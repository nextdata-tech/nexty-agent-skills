# The pre-handoff self-check script

## Contents

- What the phases are
- What this script does NOT cover
- Where an expected value may come from
- The script
- Reading a failure

## What the phases are

The dry-run for Step 7 of nxd-generate-dp, in four phases:

- **Phase A — structural check of `models.py` and `spec.py`.** Parses both files
  with `ast` and checks them against the pinned DSL surface in
  [reference/nxd-spec-api.md](nxd-spec-api.md). Nothing is imported and nothing
  is executed, because the `nxd` wheel is an internal package on a private index
  and is NOT installable here — a real import raises
  `ModuleNotFoundError: No module named 'nxd'`.
- **Phase B — dry-run of the transform** against a scratch DuckDB: the
  supervisor's execution minus the kernel.
- **Phase C — context-completeness gate** (Step 6a). Checks that `CONTEXT.md`
  exists at the closure root, that no closure file references a contract/design
  doc by a `../`-rooted path that escapes the closure, and — when
  `infra-profile.yaml` carries a populated `attributes:` list, i.e. a live
  credential in plaintext — that `.gitignore` and `SENSITIVE` exist and that
  `.gitignore` names `infra-profile.yaml`. The credential check reports missing
  FILES only; it never reads or echoes an attribute value, because a check that
  prints the secret it found turns a contained file leak into a transcript leak. A closure can be
  structurally valid and still be an insufficient handoff — a promised derived
  model whose contract lives in an external doc cannot be continued by a cold
  reader. Phase C is what catches that. (Note: the naming invariant that Phase A
  enforces already requires every promised model to be in `PHYSICAL_MODELS`, so a
  model cannot be *promised-but-deferred*; a deferred contract belongs to a model
  not yet promised, carried in `contracts/<name>.md` and `CONTEXT.md` — see
  Step 6a — until the model is authored and promised.)
- **Phase D — policy-boundary gate.** Checks that rulings are landed data the
  user can edit, not literals in transform code: `nxd_decisions`, if promised, is
  a **base** model backed by `data/` with a `status` column **and a `provenance`
  column**, each restricted to its fixed vocabulary, and no parameter in a landed
  policy CSV is duplicated as a literal in `transform/main.py`. A ledger
  generated from a Python literal *describes* the code instead of driving it —
  editing a row changes nothing, and the two silently diverge. `status` and
  `provenance` are checked independently because they answer different questions
  — *settled?* and *authored by whom?* — and a ledger carrying only the first
  cannot distinguish a weight the user supplied from a threshold you invented to
  make an underspecified rubric executable. The prose rules this enforces are in
  [derivation-plan.md](derivation-plan.md); Phase D is what makes them fire.

After the phases, the script prints a **distribution read-back** over every
derived model's classification columns. It is not a phase and it never fails the
run — it exists so a fabricated gate or verdict is visible rather than hidden
behind a green exit. Relay it (see "Reading a failure").

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

## Where an expected value may come from

SKILL.md's Step-3b invariant — *never restate the transform's arithmetic as an
assert* — extends to anything you add here, and the extension is the part that
gets violated. **An expected value comes from a landed `data/` file or from the
user's contract in `contracts/`. It never comes from the transform module or
from a copy of the transform's constants.**

Both halves matter, because complying with the first alone is the usual failure:

- `from transform.main import WEIGHTS, VERDICTS` and then asserting a weight is
  in `WEIGHTS` — fails only on a self-typo.
- `WEIGHTS = {...}` re-declared at the top of the checker, copied from the
  transform — no import, identical tautology.
- Recomputing a total with the transform's own formula over the transform's own
  constants — reproduces its arithmetic, including its errors.

None of these can detect a wrong score, a wrong gate, or a classification that
disagrees with the source. They are **internal-consistency checks**, and that is
what they must be called. Never narrate one as independent verification, and
never let a green exit stand in for "the numbers are right" — SELF-CHECK OK
means the closure is structurally sound and the transform ran, nothing more.

The good case is already the shipped one: Step-3b's Tier-1 asserts (declared-key
uniqueness, grain row count vs independently-read source rows) and Tier-2
(signed measure reconciliation in `Decimal`) all take their expected value from
the source, not from the code under test. Once a supplied rubric is landed as
data — see [derivation-plan.md](derivation-plan.md) — a check that reads the
rubric CSV is legitimately independent too.

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
AGGS = {"COUNT", "COUNT_DISTINCT", "SUM", "AVG", "MIN", "MAX", "EXPRESSION"}
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

def desc_str(node):
    """Any authored description form: literal, f-string, or concatenation.

    Adjacent parenthesised literals are folded to one Constant by the parser,
    but an f-string is a JoinedStr and a runtime `a + b` is a BinOp. Both are
    legitimately-authored descriptions, so accept them here — the acceptance
    eval's has_description() accepts them too, and the two gates must agree or
    correctly-annotated code fails one of them.
    """
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value or None
    if isinstance(node, ast.JoinedStr):
        return ast.unparse(node)
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        return ast.unparse(node)
    return None

def is_data_product_verify_call(node):
    return (isinstance(node, ast.Expr) and isinstance(node.value, ast.Call) and
            isinstance(node.value.func, ast.Attribute) and node.value.func.attr == "verify" and
            isinstance(node.value.func.value, ast.Name) and node.value.func.value.id == "data_product")

def has_main_guard(tree):
    """Require a module-level `if __name__ == "__main__"` direct verify call."""
    for node in tree.body:
        if not (isinstance(node, ast.If) and isinstance(node.test, ast.Compare) and
                isinstance(node.test.left, ast.Name) and node.test.left.id == "__name__" and
                len(node.test.ops) == len(node.test.comparators) == 1 and
                isinstance(node.test.ops[0], ast.Eq) and literal_str(node.test.comparators[0]) == "__main__"):
            continue
        if any(is_data_product_verify_call(statement) for statement in node.body):
            return True
    return False

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
    # Annotation reach, both graded as failures. A description on the WRAPPER
    # is an attribute description: it lands in data_model and never reaches
    # describe_models, so the author believes they documented the concept and
    # did not. A MISSING description is the same defect by omission — and it
    # is the one the benchmark actually measured, so warning here while the
    # eval checks fail it would leave the only mechanical gate green on
    # precisely the defect this guidance exists to prevent.
    if name in ("field", "metric_field") and any(
            k.arg == "description" and desc_str(k.value) for k in call.keywords):
        # A wrapper description is a legal attribute description (it reaches
        # the structural data_model block). The defect is using it INSTEAD of
        # the role's, so only fail when the roles carry none — otherwise this
        # would block a legal API call that is not the mistake.
        roles = [a for a in call.args[1:] if isinstance(a, ast.Call)]
        for kw in call.keywords:          # documented roles=[...] form
            if kw.arg == "roles" and isinstance(kw.value, (ast.List, ast.Tuple)):
                roles += [e for e in kw.value.elts if isinstance(e, ast.Call)]
        describable = [r for r in roles if call_name(r) in ("dimension", "metric")]
        if not any(any(k.arg == "description" and desc_str(k.value)
                       for k in r.keywords) for r in describable):
            # Point at a fix that exists. With no dimension/metric role there
            # is nowhere to move the text to — primary_key()/join() take no
            # description — so the only remedy is to delete it.
            remedy = ("move it inside dimension(...) / metric(...)"
                      if describable else
                      "primary_key()/join() take no description — drop it")
            bad(f"{where}: description= on {name}() never reaches "
                f"describe_models and the role carries none — {remedy}")
    if name in ("dimension", "metric") and not any(
            k.arg == "description" and desc_str(k.value)
            for k in call.keywords):
        bad(f"{where}: {name}() has no description= — it reaches "
            f"describe_models as a bare name the agent cannot choose on")

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
                and sub.value.id == "Agg":
            if sub.attr not in AGGS:
                bad(f"{where}: Agg.{sub.attr} is not a member "
                    f"(allowed: {sorted(AGGS)})")
            elif sub.attr == "EXPRESSION":
                # A real API member, but out of scope for this generation path:
                # its SQL lives in the output PORT model's expressions={...} map,
                # which the desktop closure does not author. Reaching for it here
                # is always an attempt to dodge a derivation — the ruling belongs
                # in the transform as a physical column or row.
                bad(f"{where}: Agg.EXPRESSION is outside this generation path — "
                    f"materialize the ruling as a physical column in the "
                    f"transform and aggregate that column with a normal Agg "
                    f"(see reference/derivation-plan.md)")
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
        # The name may be positional or the documented name= keyword — the
        # vendored example corpus writes semantic_model(name=..., description=...)
        # throughout, and best_practices.md prefers it. Missing this shape does
        # not just skip the name check, it skips the model's fields entirely.
        name_node = (root.args[0] if root.args else
                     next((k.value for k in root.keywords if k.arg == "name"), None))
        model = literal_str(name_node) if name_node is not None else None
        if model is None or not SNAKE.match(model):
            shown = ast.unparse(name_node) if name_node is not None else "<none>"
            bad(f"{path}: {kind}() name must be a lowercase snake_case string "
                f"literal, got {shown}")
            continue
        var_name[target.id], var_kind[target.id] = model, kind
        joins.setdefault(model, []); has_pk[model] = False
        # Either authoring form counts: the chained .description(...) is the
        # verified one, but the description= constructor kwarg is pinned in
        # the documented signature and is what the shipped example corpus
        # uses, so rejecting it would fail correctly-authored models.
        if kind == "semantic_model" and not (
                any(call_name(c) == "description" and c.args
                    and desc_str(c.args[0]) for c in chain)
                or any(k.arg == "description" and desc_str(k.value)
                       for k in root.keywords)):
            bad(f"{path}: semantic_model('{model}') declares no description "
                f"— both list_models and describe_model show it to the agent")
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
    # A script() is either the sole transform executor or nested inside a
    # custom verifier. Both are valid, but only the former is pinned to the
    # desktop transform entrypoint.
    verifier_scripts = set()
    for outer in ast.walk(tree):
        if not isinstance(outer, ast.Call) or call_name(outer) not in ("expectation", "promise") or not outer.args:
            continue
        chain = spine(outer.args[0])
        if not any(call_name(c) == "custom" for c in chain):
            continue
        for verify in (c for c in chain if call_name(c) == "verify" and c.args):
            verifier_scripts.update(id(c) for c in spine(verify.args[0]) if call_name(c) == "script")
    transform_scripts = {id(n) for n in ast.walk(tree) if call_name(n) == "script" and id(n) not in verifier_scripts}
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
            if id(node) in verifier_scripts:
                continue
            saw["script"] = True
            if literal_str(node.args[0] if node.args else None) != "transform/main.py":
                bad(f"{path}: script() must point at \"transform/main.py\"")
        elif n in ("compute", "secrets"):
            if any(id(c) in transform_scripts for c in spine(node)):
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
            elif n == "promise" and isinstance(arg, ast.Call) and any(
                    call_name(c) == "custom" for c in spine(arg)):
                pass  # validated as a custom promise by Phase C
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
print(f"phase B ok — transform dry-run EXECUTED; models.py/spec.py checked "
      f"STRUCTURALLY against the pinned nxd v0.41.139 DSL surface (not "
      f"executed — no nxd wheel installable here); {len(unverified)} "
      f"unverified entries listed above. A spec fault only the real wheel or "
      f"the supervisor's spec compilation can raise still reaches handoff.")

# ---------------------------------------------------------------- Phase C ---
# Context-completeness gate (Step 6a). The closure must be a SUFFICIENT handoff:
# CONTEXT.md present, and no closure file points at a contract/design doc OUTSIDE
# the closure. A structurally valid closure can still be uncontinuable if the
# rubric for a promised derived model lives in ../../some-doc.md.
cerrors = []
if not Path("CONTEXT.md").exists():
    cerrors.append("CONTEXT.md is missing from the closure root — a cold reader "
                   "cannot continue the work (intent, sample rule, inference "
                   "caveats, deferred-model contract, reopen recipe). See "
                   "reference/context-doc.md.")

# Any closure file that references a design/contract doc by a path escaping the
# closure (a ../-rooted markdown reference) is a dangling cross-boundary pointer.
# Scan the human/author-facing text files, not data.
ESCAPE = re.compile(r"\.\.(?:/[^\s\)\"']*)+\.md", re.IGNORECASE)
scan = ["CONTEXT.md", "README.md", "spec.py", "models.py", "transform/main.py"]
scan += [str(p) for p in Path("contracts").rglob("*")]
for rel in scan:
    p = Path(rel)
    if not p.is_file():
        continue
    for m in ESCAPE.findall(p.read_text()):
        cerrors.append(f"{rel}: references '{m}' — a contract/design path that "
                       f"escapes the closure. Materialize it inside the closure "
                       f"(CONTEXT.md / contracts/<name>.md / inert derived model), "
                       f"never a ../ pointer.")

# Explicit custom-contract gate. `script()` executes a whole file: every
# named contract therefore owns one verifier script, never a decorative shared
# module. This is deliberately static/offline; the Desktop runtime remains the
# authority for actually executing a verifier against its context.
spec_tree = ast.parse(spec_src, "spec.py")
custom_names, custom_scripts, custom_script_refs, input_custom = [], set(), [], 0
for node in ast.walk(spec_tree):
    if not isinstance(node, ast.Call):
        continue
    if call_name(node) == "custom":
        name = literal_str(node.args[0] if node.args else None)
        if not name:
            cerrors.append("spec.py: custom() name must be a string literal")
        else:
            custom_names.append(name)
    if call_name(node) in ("expectation", "promise") and node.args:
        chain = spine(node.args[0])
        if any(call_name(c) == "custom" for c in chain):
            if call_name(node) == "expectation":
                input_custom += 1
            verify_calls = [c for c in chain if call_name(c) == "verify" and c.args]
            scripts = [c for verify in verify_calls for c in spine(verify.args[0])
                       if call_name(c) == "script"]
            if len(scripts) != 1:
                cerrors.append(f"spec.py: custom {call_name(node)} needs one script(...)")
            else:
                script_path = literal_str(scripts[0].args[0] if scripts[0].args else None)
                if not script_path or not script_path.startswith("contracts/") or ".." in script_path or Path(script_path).is_absolute():
                    cerrors.append(f"spec.py: custom verifier path must stay under contracts/, got {script_path!r}")
                else:
                    custom_scripts.add(script_path)
                    custom_script_refs.append(script_path)
            if not any(call_name(c) == "compute" for verify in verify_calls
                       for c in spine(verify.args[0])):
                cerrors.append(f"spec.py: custom {call_name(node)} verifier needs script(...).compute(_compute)")
            elif not all(call_name(verify.args[0]) == "compute" and verify.args[0].args and
                         isinstance(verify.args[0].args[0], ast.Name) and
                         verify.args[0].args[0].id == "_compute" for verify in verify_calls):
                cerrors.append(f"spec.py: custom {call_name(node)} must use exact script(...).compute(_compute) nesting")
            if not any(call_name(c) == "description" and c.args and desc_str(c.args[0]) for c in chain):
                cerrors.append(f"spec.py: custom {call_name(node)} needs a non-empty description")
            if not any(call_name(c) == "model" and c.args and isinstance(c.args[0], ast.Name) and
                       c.args[0].id in var_name for c in chain):
                cerrors.append(f"spec.py: custom {call_name(node)} needs one resolved models.py model")
if len(custom_names) != len(set(custom_names)):
    cerrors.append(f"spec.py: custom contract names are not unique: {custom_names}")
if len(custom_script_refs) != len(set(custom_script_refs)):
    cerrors.append("spec.py: each named custom contract needs its own verifier script")

# The merged Desktop runtime only supports the unlabeled local-file service for
# source-aligned inputs. Labeled CSV services remain valid transform secrets,
# but they cannot be bound through `.input(...).source(...)` yet. Check this
# for every source-aligned input, not just custom expectations: otherwise a
# non-custom input could compile against the wrong runtime service/driver.
csv_ref = "/infra-profile/desktop-local#/services/csv-source"
csv_bindings = [literal_str(node.value) for node in spec_tree.body
                if isinstance(node, ast.Assign) and
                any(isinstance(target, ast.Name) and target.id == "_csv"
                    for target in node.targets)]
csv_binding = csv_bindings[0] if len(csv_bindings) == 1 else None
source_aligned_inputs = 0
for node in ast.walk(spec_tree):
    if call_name(node) != "input" or len(node.args) < 2:
        continue
    chain = spine(node.args[1])
    if not any(call_name(c) == "source_aligned_input" for c in chain):
        continue
    source_aligned_inputs += 1
    source_calls = [c for c in chain if call_name(c) == "source" and c.args]
    if (len(source_calls) != 1 or
            not isinstance(source_calls[0].args[0], ast.Name) or
            source_calls[0].args[0].id != "_csv" or csv_binding != csv_ref):
        cerrors.append(
            "spec.py: Pocket source-aligned inputs currently require "
            ".source(_csv) bound exactly to "
            "/infra-profile/desktop-local#/services/csv-source; labeled CSV "
            "services are transform-only on this runtime."
        )

csv_root = Path("data")
if input_custom:
    csv_source_path = Path("csv-source-path")
    csv_root_text = csv_source_path.read_text().strip() if csv_source_path.is_file() else ""
    csv_root_parts = csv_root_text.replace("\\", "/").split("/") if csv_root_text else []
    if (not csv_root_text or Path(csv_root_text).is_absolute() or
            any(part in ("", ".", "..") for part in csv_root_parts) or
            not Path(csv_root_text).is_dir()):
        cerrors.append("csv-source-path: custom CSV input requires an existing contained relative export root")
    else:
        csv_root = Path(csv_root_text)
# Check each custom at its enclosing declaration, rather than accepting an
# unrelated source_aligned_input()/duckdb port elsewhere in the spec.
for node in ast.walk(spec_tree):
    if call_name(node) == "input" and len(node.args) >= 2:
        config = node.args[1]
        has_custom = any(call_name(n) == "expectation" and n.args and
                         any(call_name(c) == "custom" for c in spine(n.args[0]))
                         for n in ast.walk(config) if isinstance(n, ast.Call))
        if has_custom:
            custom_models = [c.args[0].id for n in ast.walk(config)
                             if isinstance(n, ast.Call) and call_name(n) == "expectation" and n.args and
                             any(call_name(part) == "custom" for part in spine(n.args[0]))
                             for c in spine(n.args[0]) if call_name(c) == "model" and c.args and
                             isinstance(c.args[0], ast.Name)]
            chain = spine(config)
            source_calls = [c for c in chain if call_name(c) == "source" and c.args]
            model_path_calls = [c for c in chain if call_name(c) == "config" and c.args and
                                isinstance(c.args[0], ast.Dict) and any(
                                    literal_str(k) == "model_paths" for k in c.args[0].keys)]
            if not any(call_name(c) == "source_aligned_input" for c in chain) or not source_calls:
                cerrors.append("spec.py: custom input expectation must be on its source_aligned_input declaration")
            if not model_path_calls:
                cerrors.append("spec.py: custom CSV input expectation needs .config({model_paths: ...})")
            else:
                model_paths, found_mapping = {}, False
                for call in model_path_calls:
                    for key, value in zip(call.args[0].keys, call.args[0].values):
                        if literal_str(key) != "model_paths":
                            continue
                        found_mapping = True
                        if not isinstance(value, ast.Dict) or not value.keys:
                            cerrors.append("spec.py: custom CSV input model_paths must be a non-empty literal mapping")
                            continue
                        for model_key, path_value in zip(value.keys, value.values):
                            model_key, path = literal_str(model_key), literal_str(path_value)
                            components = path.replace("\\", "/").split("/") if path else []
                            if (not model_key or not model_key.strip() or not path or Path(path).is_absolute() or
                                    path.endswith("/") or not path.endswith(".csv") or
                                    any(part in ("", ".", "..") for part in components)):
                                cerrors.append("spec.py: custom CSV input model_paths must use non-empty model keys and contained relative .csv paths")
                                continue
                            model_paths[model_key] = path
                if not found_mapping:
                    cerrors.append("spec.py: custom CSV input model_paths must be a non-empty literal mapping")
                for model_name in custom_models:
                    path = model_paths.get(model_name)
                    if not path:
                        cerrors.append(f"spec.py: custom CSV input model_paths[{model_name!r}] must be a safe relative path")
                    elif not (csv_root / path).is_file():
                        cerrors.append(f"spec.py: custom CSV input model_paths[{model_name!r}] must resolve to an existing csv-source-path/*.csv file")
    if call_name(node) == "output" and node.args:
        config = node.args[0]
        has_custom = any(call_name(n) == "promise" and n.args and
                         any(call_name(c) == "custom" for c in spine(n.args[0]))
                         for n in ast.walk(config) if isinstance(n, ast.Call))
        if has_custom:
            chain = spine(config)
            ordinary = any(call_name(n) == "promise" and n.args and isinstance(n.args[0], ast.Name)
                           and n.args[0].id in var_name for n in chain)
            port = next((c for c in chain if call_name(c) == "port"), None)
            if not ordinary:
                cerrors.append("spec.py: custom output promise must retain ordinary .promise(model)")
            valid_duckdb_port = (port and literal_str(port.args[0] if port.args else None) == "duckdb" and
                                 len(port.args) >= 2 and call_name(port.args[1]) == "storage" and
                                 port.args[1].args and isinstance(port.args[1].args[0], ast.Name) and
                                 port.args[1].args[0].id == "_duckdb")
            if not valid_duckdb_port:
                cerrors.append("spec.py: custom output promise must be on its DuckDB output declaration")
for script_path in custom_scripts:
    p = Path(script_path)
    if not p.is_file():
        cerrors.append(f"{script_path}: referenced custom verifier is missing")
        continue
    try:
        tree = ast.parse(p.read_text(), script_path)
    except SyntaxError as exc:
        cerrors.append(f"{script_path}: verifier cannot be imported (syntax error: {exc.msg})")
        continue
    registered = sum(any(call_name(d) == "on_verify" for d in n.decorator_list)
                     for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)))
    main_calls_verify = has_main_guard(tree)
    if registered != 1 or not main_calls_verify:
        cerrors.append(f"{script_path}: needs exactly one @data_product.on_verify() and data_product.verify() main guard")
    verifier = next((n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
                     and any(call_name(d) == "on_verify" for d in n.decorator_list)), None)
    verifier_src = ast.unparse(verifier) if verifier else ""
    conditional_failed = verifier and any(
        not isinstance(branch.test, ast.Constant) and any(
            isinstance(result, ast.Return) and result.value is not None and
            "VerifyResultEnum.FAILED" in ast.unparse(result.value)
            for result in ast.walk(branch))
        for branch in ast.walk(verifier) if isinstance(branch, ast.If))
    inert = (not verifier or any(isinstance(n, ast.Pass) or
             (isinstance(n, ast.Expr) and isinstance(n.value, ast.Constant) and n.value.value is Ellipsis)
             for n in ast.walk(verifier)) or "VerifyResultEnum.FAILED" not in verifier_src or
             "VerifyResultEnum.PASS" not in verifier_src or not conditional_failed)
    if inert:
        cerrors.append(f"{script_path}: verifier is inert — require FAILED behind a non-literal condition and a PASS result, never pass/ellipsis/dead branches")
    if re.search(r'(?i)(api[_-]?key|password|token|secret)\s*=\s*["\']', p.read_text()):
        cerrors.append(f"{script_path}: contains a literal secret-like assignment")
for p in Path("contracts").rglob("*.py") if Path("contracts").exists() else []:
    if str(p) not in custom_scripts:
        cerrors.append(f"{p}: decorative custom verifier is not referenced by spec.py")

# Sensitivity artifacts. The trigger is STRUCTURAL: a *-source service carrying
# a populated `attributes:` list holds a live credential in plaintext. A CSV or
# file source keeps `attributes: []` and is exempt, so this cannot false-positive
# on a healthy local closure. Names the missing FILES only — never reads or
# echoes an attribute value, because a check that prints the secret it found
# turns a contained file leak into a transcript leak.
profile = Path("infra-profile.yaml")
if profile.exists():
    text = profile.read_text()
    if not re.search(r"(?m)^metadata:\s*\n\s+name:\s*desktop-local\s*$", text):
        cerrors.append("infra-profile.yaml: metadata.name must be desktop-local to match spec.py infra_profile")
    def has_service_driver(service, driver):
        block = re.search(rf"(?ms)^\s*-\s*name:\s*{re.escape(service)}\s*$((?:(?!^\s*-\s*name:).)*)", text)
        return bool(block and re.search(rf"^\s*driver:\s*{re.escape(driver)}\s*$", block.group(1), re.MULTILINE))
    required_services = {
        "duckdb": "nxd:local/duckdb/storage:0.1.0",
        "python-compute": "nxd:local/python/compute:0.1.0",
    }
    if source_aligned_inputs:
        required_services["csv-source"] = "nxd:local/file/storage:0.1.0"
    for service, driver in required_services.items():
        if not has_service_driver(service, driver):
            cerrors.append(f"infra-profile.yaml: {service} must use {driver}")
    # A populated attributes list = `attributes:` followed by a `- ` item before
    # the next key at the same or shallower indent. `attributes: []` never matches.
    # Match every YAML spelling of a populated list, because a gate that only
    # recognises the shipped templates is not the structural check it claims to
    # be — an improvised profile carries exactly the same live credential:
    #   block, indented      `attributes:` / `  - key: ...`   (what templates emit)
    #   block, zero-indent   `attributes:` / `- key: ...`     (also valid YAML)
    #   inline flow          `attributes: [{key: ...}]`
    # `attributes: []` and `attributes: [ ]` must NOT match in any form.
    has_secret = (
        re.search(r"^\s*attributes:\s*\n\s*-\s", text, re.MULTILINE) is not None
        or re.search(r"^\s*attributes:\s*\[\s*[^\s\]]", text, re.MULTILINE) is not None
    )
    if has_secret:
        for name, why in (
            (".gitignore", "git will happily commit infra-profile.yaml without it"),
            ("SENSITIVE", "a cold reader gets no warning before opening the closure"),
        ):
            if not Path(name).exists():
                cerrors.append(
                    f"{name} is missing, but infra-profile.yaml carries a populated "
                    f"`attributes:` list (a live credential in plaintext) — {why}. "
                    f"See reference/database-source.md, 'Sensitivity artifacts'.")
        gi = Path(".gitignore")
        if gi.exists() and "infra-profile.yaml" not in gi.read_text():
            cerrors.append(
                ".gitignore exists but does not ignore infra-profile.yaml — the one "
                "file that must never be committed. Ignore it by name, never `*`.")

if cerrors:
    print("\nPHASE C FAILED — context-completeness gate:")
    for e in cerrors:
        print(f"  - {e}")
    sys.exit(1)
print("phase C ok — CONTEXT.md present, custom contracts are wired, and no closure-escaping contract references")

# ---------------------------------------------------------------- Phase D ---
# Policy-boundary gate. A ruling is landed data the user can edit, never a
# literal in transform code. Both halves are checked, because complying with
# either alone leaves the defect intact:
#   (a) nxd_decisions, if promised, is a BASE model backed by data/ with a
#       status column AND a provenance column — not a derived model generated
#       from a Python literal, which produces a ledger that DESCRIBES code
#       rather than driving it. status and provenance are orthogonal axes
#       (settled-or-not vs authored-by), so both are required: a ledger with
#       only status cannot tell a weight the user supplied from a threshold the
#       agent invented to fill an underspecified rubric;
#   (b) no value in a landed policy CSV also appears as a literal in
#       transform/main.py — a duplicated threshold silently diverges from the
#       row that claims to be editable.
# Ground truth is the closure's own landed data, so this needs no fixture.
derrors = []

# Use the values Phase B IMPORTED, not the statically-parsed ones: the template
# writes PHYSICAL_MODELS = BASE_MODELS + DERIVED_MODELS, which is an expression
# rather than a literal, so the static reader reports it `unverified` and a gate
# keyed on it would silently never fire.
if "nxd_decisions" in set(PHYSICAL_MODELS):
    if "nxd_decisions" not in set(BASE_MODELS):
        derrors.append(
            "nxd_decisions is promised but is not in BASE_MODELS — it is being "
            "generated in the transform. A ledger built from a Python literal "
            "describes the code instead of driving it: editing a row changes "
            "nothing. Write data/nxd_decisions/nxd_decisions.csv and land it "
            "like any other base model (reference/derivation-plan.md).")
    else:
        led = Path("data/nxd_decisions/nxd_decisions.csv")
        if not led.exists():
            derrors.append("nxd_decisions is in BASE_MODELS but "
                           "data/nxd_decisions/nxd_decisions.csv is missing.")
        else:
            import csv as _csv
            with led.open(newline="") as fh:
                lrows = list(_csv.DictReader(fh))
            # status and provenance are checked INDEPENDENTLY: they are separate
            # axes, so a missing provenance column must not skip status
            # validation (or the reverse). Each column: present, then in-vocab.
            LEDGER_VOCAB = {
                "status": ({"confirmed", "proposed", "blocked"},
                           "status is how a user tells a settled ruling from an "
                           "open one"),
                "provenance": ({"user_confirmed", "agent_authored",
                                "source_derived", "deferred"},
                               "provenance is how a reviewer tells a value the "
                               "USER supplied from one the AGENT invented to "
                               "fill an underspecified rubric — status does not "
                               "carry that, it is a different axis"),
            }
            for lcol, (okvals, why) in LEDGER_VOCAB.items():
                if lrows and lcol not in lrows[0]:
                    derrors.append(
                        f"nxd_decisions.csv has no {lcol!r} column (found "
                        f"{sorted(lrows[0])}). {why}. Allowed values are "
                        f"{sorted(okvals)} (reference/derivation-plan.md).")
                    continue
                badv = {(r[lcol] or "").strip() for r in lrows} - okvals
                if badv:
                    derrors.append(
                        f"nxd_decisions.{lcol} has {sorted(badv)}; allowed "
                        f"values are {sorted(okvals)}. The vocabulary is fixed: "
                        f"a value outside it is not queryable as a class.")

# (b) A policy value that is landed AND hardcoded is a divergence waiting to
# happen. Only scan CSVs whose model name looks like landed policy, and only
# compare distinctive values: short/common tokens ("1", "US", "PASS") collide by
# coincidence, and flagging those would make this unreliable.
POLICY_HINT = ("rubric", "weight", "threshold", "band", "anchor", "verdict",
               "scale", "policy", "gate", "criteri")
tsrc = Path("transform/main.py").read_text()
tlits = set()
for node in ast.walk(ast.parse(tsrc)):
    if isinstance(node, ast.Constant):
        if isinstance(node.value, str):
            tlits.add(node.value.strip())
        elif isinstance(node.value, (int, float)) and not isinstance(node.value, bool):
            tlits.add(str(node.value))
# A KEY column is how the transform looks a row UP, so naming it in code is
# correct and expected ("c1_backend_depth" as an output column). What must not
# be duplicated is the PARAMETER the row carries — the weight, threshold or
# verdict the lookup returns. Skip the first column and any *_id/key/name/
# criterion column; check the rest.
KEYISH = ("id", "key", "name", "criterion", "code", "slug", "label")
for pcsv in sorted(Path("data").rglob("*.csv")):
    if not any(h in pcsv.parent.name.lower() for h in POLICY_HINT):
        continue
    import csv as _csv
    with pcsv.open(newline="") as fh:
        prows = list(_csv.DictReader(fh))
    if not prows:
        continue
    cols = list(prows[0])
    for col in cols[1:]:                       # first column is the key
        if any(k in col.lower() for k in KEYISH):
            continue
        for row in prows:
            v = (row[col] or "").strip()
            # Distinctive = long enough to be a real policy value, or a
            # decimal/multi-digit number. Single digits and 1-3 char codes
            # collide with array indices and unrelated strings.
            distinctive = len(v) >= 4 or (
                v.replace(".", "", 1).isdigit() and len(v) >= 2)
            if distinctive and v in tlits:
                derrors.append(
                    f"{pcsv}: value {v!r} (column '{col}') is landed AND "
                    f"appears as a literal in transform/main.py. The "
                    f"transform must READ it from the row; a copy diverges "
                    f"from the row the user edits.")

if derrors:
    print("\nPHASE D FAILED — policy boundary (rulings are data, not code):")
    for e in dict.fromkeys(derrors):
        print(f"  - {e}")
    sys.exit(1)
print("phase D ok — rulings land as editable data with status + provenance, "
      "not transform literals")
print("SELF-CHECK OK — Phases A (structural), B (transform dry-run), "
      "C (context-completeness), D (policy boundary) all passed.")

# Distribution read-back. NOT a gate — it never fails the run. It prints the
# value counts of every classification-shaped string column of every derived
# model, so a fabricated gate or verdict is visible instead of hiding behind a
# green exit. Unconditional by design: deciding which columns "matter" is the
# judgement that would make this unreliable. A column qualifies on shape alone —
# it must actually GROUP (few distinct values, and fewer than one per row), which
# excludes keys and free text without naming either. Relay these counts to the
# user before the build (see nxd-pocket-loop Step 3).
for m in sorted(set(PHYSICAL_MODELS) - set(BASE_MODELS)):
    n_rows = con.execute(f"SELECT COUNT(*) FROM main.{m}").fetchone()[0]
    cols = [r[0] for r in con.execute(
        f"SELECT name FROM pragma_table_info('{m}') WHERE type = 'VARCHAR'").fetchall()
        if not r[0].startswith("_dlt_")]  # dlt bookkeeping, not model data
    for c in cols:
        rows = con.execute(f'SELECT "{c}", COUNT(*) FROM main.{m} '
                           f'GROUP BY 1 ORDER BY 2 DESC').fetchall()
        if not (len(rows) <= 12 and len(rows) * 2 <= n_rows):
            continue  # a key or free text, not a classification
        counts = ", ".join(f"{v!r}={n}" for v, n in rows)
        flag = "  <- UNIFORM: this column does not discriminate" if len(rows) == 1 else ""
        print(f"distribution {m}.{c}: {counts}{flag}")

# Declared-but-absent read-back. The dual of UNIFORM, and equally unconditional:
# a vocabulary the closure LANDS (verdict labels, statuses, buckets) whose value
# never appears in any derived column is a branch that did not fire. Deciding
# whether it CANNOT fire needs reasoning and stays with you — this only reports
# what is mechanically true: declared, never produced. Vocabularies come from
# landed data, never from a transform literal, so this is independent of the
# code it is checking.
produced = set()
for m in sorted(set(PHYSICAL_MODELS) - set(BASE_MODELS)):
    for (c,) in con.execute(
            f"SELECT name FROM pragma_table_info('{m}') "
            f"WHERE type = 'VARCHAR'").fetchall():
        if c.startswith("_dlt_"):
            continue
        produced |= {str(v[0]).strip() for v in con.execute(
            f'SELECT DISTINCT "{c}" FROM main.{m}').fetchall() if v[0] is not None}
VOCAB_HINT = ("verdict", "bucket", "outcome", "band", "tier", "category")
for vcsv in sorted(Path("data").rglob("*.csv")):
    # nxd_decisions is the ledger ABOUT the policy, not an output vocabulary:
    # its own status values are meant to describe rulings, not to appear in a
    # scored row. Reporting them absent would be noise on every closure.
    if vcsv.parent.name == "nxd_decisions":
        continue
    import csv as _csv
    with vcsv.open(newline="") as fh:
        vrows = list(_csv.DictReader(fh))
    for col in (vrows[0] if vrows else {}):
        if not any(h in col.lower() for h in VOCAB_HINT):
            continue
        declared = {(r[col] or "").strip() for r in vrows} - {""}
        missing = sorted(d for d in declared if d not in produced)
        if missing and len(declared) <= 12:
            print(f"ABSENT {vcsv.parent.name}.{col}: declared {missing} — "
                  f"never produced in any derived column")
```

The read-back prints **after** `SELF-CHECK OK`, deliberately: it is the last
thing on screen, and it is not what the OK line attests to. Read it before you
report the run — a gate that passed every row, or a verdict that came out
single-valued, is a number you invented, and it is now the last thing you saw
rather than the thing the success banner scrolled past.

## Reading a failure

The row counts printed for derived models are worth reading, not just passing:
a derived table with zero rows, or with exactly as many rows as its source when
the derivation was supposed to expand or collapse, means the derivation ran but
did nothing. The Step-3b asserts should have caught that — if they did not, the
invariant they encode was too weak.

Reading a **Phase D** failure: it is not a formatting complaint. `nxd_decisions
is promised but is not in BASE_MODELS` means the ledger is generated from a
Python literal, so it documents the code rather than driving it — the row a user
edits has no effect, and the two drift apart the moment either changes. Fix it by
writing `data/nxd_decisions/nxd_decisions.csv` and reading it like any other base
model, never by deleting the model or loosening the check. `value X is landed AND
appears as a literal` means the same value exists in two places that can
disagree: delete the literal and read the row.

`nxd_decisions.csv has no 'provenance' column` means the ledger records whether
each ruling is settled but not who wrote it — so a reviewer cannot separate the
user's weights from the ones you invented. Add the column and classify **every**
row from the fixed set; do not backfill them all as `user_confirmed` to clear the
gate, which is the exact erasure the column exists to prevent. `provenance has
[...]` means a value outside that set: the vocabulary is closed precisely so the
class is queryable, so map your value onto one of the four rather than widening
the set. Which value belongs on which row is in
[derivation-plan.md](derivation-plan.md).

An **ABSENT** line reports a declared value no derived column ever produced. It
is mechanical and says only that: on this data, that branch did not fire. Whether
it *cannot* fire is yours to work out — and if a rule makes a verdict
unreachable (a criterion that can never reach the score its own branch needs),
say so to the user rather than shipping a branch that is dead by construction.

The **distribution read-back** is read the same way, and it is the one the
success banner is most likely to bury. A `UNIFORM` line means a column you built
to distinguish rows does not: a gate that passes every row is not a gate, and a
classification with one value classified nothing. That is a value you supplied,
not one the data produced. Two things follow. **State the distribution to the
user before building** — a uniform gate by name, and what it was supposed to
separate. And do not silently repair it: a gate that cannot fail is a ruling you
authored, so it lands in `nxd_decisions` like any other, or it goes back to the
user as a question. A non-uniform distribution is not a pass either — it is
simply the shape of what you produced, and it is worth one line in the handoff.

Reading a Phase A failure: every message names the file, model, and column. A
kwarg rejection (`join() takes to=, not to_model=`) is a typo — fix the call. A
naming-invariant failure is a diverged name — fix the NAME in every place it
appears (`models.py`, `.promise`, `PHYSICAL_MODELS`, `data/<name>/`), never
quote around it. If a message contradicts the installed wheel's actual
behaviour, the pin has drifted: re-derive that one signature, and update
`nxd-spec-api.md` and this script together.

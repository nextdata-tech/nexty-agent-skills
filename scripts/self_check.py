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
    # Annotation reach, both graded as failures. A description on the WRAPPER
    # is an attribute description: it lands in data_model and never reaches
    # describe_models, so the author believes they documented the concept and
    # did not. A MISSING description is the same defect by omission — and it
    # is the one the benchmark actually measured, so warning here while the
    # eval checks fail it would leave the only mechanical gate green on
    # precisely the defect this guidance exists to prevent.
    if name in ("field", "metric_field") and any(
            k.arg == "description" for k in call.keywords):
        bad(f"{where}: description= on {name}() never reaches describe_models "
            f"— move it inside dimension(...) / metric(...)")
    if name in ("dimension", "metric") and not any(
            k.arg == "description" and literal_str(k.value)
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
        # Either authoring form counts: the chained .description(...) is the
        # verified one, but the description= constructor kwarg is pinned in
        # the documented signature and is what the shipped example corpus
        # uses, so rejecting it would fail correctly-authored models.
        if kind == "semantic_model" and not (
                any(call_name(c) == "description" for c in chain)
                or any(k.arg == "description" and literal_str(k.value)
                       for k in root.keywords)):
            bad(f"models.py: semantic_model('{model}') declares no description "
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
scan += [str(p) for p in Path(".").glob("contracts/*")]
for rel in scan:
    p = Path(rel)
    if not p.exists():
        continue
    for m in ESCAPE.findall(p.read_text()):
        cerrors.append(f"{rel}: references '{m}' — a contract/design path that "
                       f"escapes the closure. Materialize it inside the closure "
                       f"(CONTEXT.md / contracts/<name>.md / inert derived model), "
                       f"never a ../ pointer.")

# Sensitivity artifacts. The trigger is STRUCTURAL: a *-source service carrying
# a populated `attributes:` list holds a live credential in plaintext. A CSV or
# file source keeps `attributes: []` and is exempt, so this cannot false-positive
# on a healthy local closure. Names the missing FILES only — never reads or
# echoes an attribute value, because a check that prints the secret it found
# turns a contained file leak into a transcript leak.
profile = Path("infra-profile.yaml")
if profile.exists():
    text = profile.read_text()
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
print("phase C ok — CONTEXT.md present, no closure-escaping contract references")

# ---------------------------------------------------------------- Phase D ---
# Policy-boundary gate. A ruling is landed data the user can edit, never a
# literal in transform code. Both halves are checked, because complying with
# either alone leaves the defect intact:
#   (a) nxd_decisions, if promised, is a BASE model backed by data/ with a
#       status column — not a derived model generated from a Python literal,
#       which produces a ledger that DESCRIBES code rather than driving it;
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
            if lrows and "status" not in lrows[0]:
                derrors.append(
                    f"nxd_decisions.csv has no 'status' column (found "
                    f"{sorted(lrows[0])}). status is the whole mechanism: it is "
                    f"how a user tells a confirmed ruling from one you proposed.")
            else:
                okst = {"confirmed", "proposed", "blocked"}
                badst = {r["status"] for r in lrows} - okst
                if badst:
                    derrors.append(f"nxd_decisions.status has {sorted(badst)}; "
                                   f"allowed values are {sorted(okst)}.")

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
print("phase D ok — rulings land as editable data, not transform literals")
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

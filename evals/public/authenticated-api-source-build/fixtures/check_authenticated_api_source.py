"""Deterministic checks for the authenticated-api-source-build scenario.

This checker re-materializes the closure's own transform against a FRESH
instance of the same stub the agent built against (the runner's own instance is
already torn down by the time this checker runs — see http_stub_server() in
run.py) and inspects the landed DuckDB, plus static reads of the closure
source and infra-profile.yaml. Nothing here supplies numbers the transform
itself did not produce; the stub is the only synthetic input, and it is
identical in shape (routes, auth, payload, traps) to the one the agent used.

Why this can grade what the judge cannot on its own: the two central claims —
"the credential really reaches an Authorization header" and "the pagination /
nested-field / orphan-monitor traps are actually handled" — are decidable only
by running the ingestion and reading the landed rows, not by reading the
transcript.

Run from the closure root with the fixtures directory passed in:

    python check_authenticated_api_source.py --fixtures <path-to-fixtures>
"""

from __future__ import annotations

import argparse
import ast
import importlib.util
import json
import os
import re
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
from pathlib import Path

FAILURES: list[str] = []
PASSES: list[str] = []

MATERIALIZE_TIMEOUT_S = 300
VALID_TOKEN = "bcn_live_9f3ac2e7d84b41f0a6c5d2e19b7f0033"


def check(name: str, ok: bool, detail: str = "") -> bool:
    (PASSES if ok else FAILURES).append(name if ok else f"{name}: {detail}".rstrip(": "))
    return ok


def print_report() -> None:
    for name in PASSES:
        print(f"PASS {name}")
    for name in FAILURES:
        print(f"FAIL {name}")
    print()
    print(f"{len(PASSES)} passed, {len(FAILURES)} failed")
    if not FAILURES:
        print("ALL CHECKS PASSED")


def load_stub(fixtures: Path):
    """Import stub_beacon_api.py directly from the fixtures dir."""
    module_path = fixtures / "stub_beacon_api.py"
    spec = importlib.util.spec_from_file_location("_stub_beacon_api", module_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


# ---------------------------------------------------------------------------
# Static source checks — no live server needed.
# ---------------------------------------------------------------------------


def no_literal_secret_in_source(root: Path) -> tuple[bool, str]:
    """The bearer token must never appear as a literal in any committed source
    file — only inside infra-profile.yaml, which the sensitivity artifacts
    (.gitignore/SENSITIVE) exist to keep out of a commit."""
    hits = []
    for rel in ("spec.py", "models.py", "requirements.txt"):
        p = root / rel
        if p.is_file() and VALID_TOKEN in p.read_text(encoding="utf-8", errors="replace"):
            hits.append(rel)
    for p in sorted((root / "transform").glob("*.py")) if (root / "transform").is_dir() else []:
        if VALID_TOKEN in p.read_text(encoding="utf-8", errors="replace"):
            hits.append(str(p.relative_to(root)))
    return not hits, f"token literal found in {hits}" if hits else ""


def profile_attributes(root: Path) -> tuple[dict[str, str], dict[str, str]]:
    """Every `key:`/`value:`/`public:` attribute in infra-profile.yaml, flat.

    Returns ({key: value}, {key: public-flag-lowercased}). Recovered with a
    permissive line-based read -- this is a fixture-authored YAML, not a
    document we need a real parser for.

    Flat across services on purpose: that is exactly what the supervisor does
    when it merges every service in `.secrets([...])` into the transform's
    `secrets` map, so a checker keyed on service boundaries would be measuring
    a structure the transform never sees. Returns empty maps for a missing file
    -- callers check for the file itself.
    """
    profile = root / "infra-profile.yaml"
    if not profile.is_file():
        return {}, {}
    text = profile.read_text(encoding="utf-8", errors="replace")
    fields: dict[str, str] = {}
    public_flags: dict[str, str] = {}
    cur_key = None
    for line in text.splitlines():
        m = re.match(r"^\s*-?\s*key:\s*(\S+)", line)
        if m:
            cur_key = m.group(1)
            continue
        m = re.match(r"^\s*value:\s*(.+?)\s*$", line)
        if m and cur_key:
            fields[cur_key] = m.group(1).strip("'\"")
            continue
        # `public` may precede or follow `value` within the same entry, so the
        # key stays current until the next `key:` rather than being cleared by
        # whichever of the two is seen first.
        m = re.match(r"^\s*public:\s*(\S+)", line)
        if m and cur_key:
            public_flags[cur_key] = m.group(1).strip("'\"").lower()
    return fields, public_flags


def infra_profile_has_structured_auth(root: Path) -> tuple[bool, str, dict]:
    """infra-profile.yaml's api-source service must carry auth_type: bearer +
    auth_token as flat attributes -- never the whole credential nested under
    one opaque value, and never omitted (this API requires auth)."""
    profile = root / "infra-profile.yaml"
    if not profile.is_file():
        return False, "infra-profile.yaml missing", {}
    text = profile.read_text(encoding="utf-8", errors="replace")
    if "api-source" not in text:
        return False, "no api-source service declared", {}
    if "auth_type" not in text or "bearer" not in text:
        return False, "no auth_type: bearer attribute found", {}
    if "auth_token" not in text:
        return False, "no auth_token attribute found", {}
    fields, public_flags = profile_attributes(root)
    if fields.get("auth_token") != VALID_TOKEN:
        return False, f"auth_token attribute does not match the brief's token (got {fields.get('auth_token')!r})", fields
    if "base_url" not in fields:
        return False, "no base_url attribute found", fields
    # A credential marked public survives export, which is the whole reason the
    # flag exists. checks.json states this as a FAIL condition and tells the
    # judge to grade from this fact, so the fact has to actually carry it.
    if public_flags.get("auth_token") == "true":
        return False, ("auth_token is marked public: true — the credential would "
                       "survive export; a secret attribute must be public: false"), fields
    return True, "", fields


def sensitivity_artifacts_present(root: Path) -> tuple[bool, str]:
    missing = [n for n in (".gitignore", "SENSITIVE") if not (root / n).is_file()]
    if missing:
        return False, f"missing {missing} despite a populated api-source attributes list"
    gi = (root / ".gitignore").read_text(encoding="utf-8", errors="replace")
    if "infra-profile.yaml" not in gi:
        return False, ".gitignore does not ignore infra-profile.yaml"
    return True, ""


def auth_is_dispatched_on_auth_type(transform_src: str) -> tuple[bool, str]:
    """The transform must READ auth_type and branch on it, not hardcode one scheme.

    The natural shortcut is to write only the branch today's profile needs —
    ``client_config["auth"] = {"type": "bearer", ...}`` with no ``auth_type``
    read at all. It works, which is why nothing catches it: the profile still
    carries ``auth_type`` as an attribute, so the closure claims to be
    configured by a field it ignores. Flip the profile to ``http_basic`` and the
    transform keeps sending a bearer header built from a now-absent field.

    Graded here rather than by the judge because it is a property of the landed
    source, and a judge reading a transcript can only see it if the agent
    happened to echo the file.

    Deliberately structural, not a string match on ``"bearer"``: a closure may
    legitimately support one scheme, so long as it DISPATCHES — reads the field,
    and rejects a value it cannot serve. Hardcoding is the finding; supporting a
    subset is not.
    """
    reads = bool(re.search(r"""\[["']auth_type["']\]|\.get\(\s*["']auth_type["']""",
                           transform_src))
    if not reads:
        return False, ('transform never reads secrets["auth_type"] — '
                       "the auth dict is hardcoded to one scheme while the profile "
                       "carries auth_type as a configurable attribute")
    branches = bool(re.search(r"\bif\b[^\n]*auth_type|\belif\b[^\n]*auth_type",
                              transform_src))
    if not branches:
        return False, ("auth_type is read but never branched on — the value is "
                       "fetched and ignored, which is the hardcoded case wearing "
                       "a read")
    # An unhandled auth_type must fail loudly. Without this the closure silently
    # sends no auth (or the wrong scheme) and the 401 reads as a bad credential.
    #
    # Scoped to the dispatch's own region, not the whole file: every transform
    # this pack generates carries a read-back assert near the end, so a
    # file-wide `raise|assert` search passes on that alone and this branch would
    # never fire. Take the source from the first auth_type mention to the config
    # assembly that consumes it.
    # The end anchor is searched FROM the dispatch, not from offset 0. The
    # taught template imports RESTAPIConfig on its first line — before any
    # auth_type — so a search from 0 always lands ahead of `start`, the region
    # collapses to the 2000-char fallback, and the read-back assert ~1.5k chars
    # later satisfies the pattern. That is the never-fires bug this scoping
    # exists to avoid, reintroduced by the anchor.
    start = re.search(r"""auth_type""", transform_src)
    if not start:
        region = ""
    else:
        tail = transform_src[start.end():]
        end = re.search(r"""RESTAPIConfig|["']resources["']\s*:""", tail)
        region = tail[:end.start()] if end else tail[:2000]
    rejects = bool(re.search(r"\b(raise|assert)\b", region))
    if not rejects:
        return False, ("auth_type is dispatched but no branch rejects an "
                       "unsupported value — an auth_type the transform cannot "
                       "serve should raise at transform time, not surface as a 401")
    return True, ""


def uses_rest_api_resources(transform_src: str) -> tuple[bool, str]:
    """The transform must go through dlt's REST connector, not a hand-rolled
    requests/urllib loop fed to dlt as a plain generator."""
    has_rest_import = bool(re.search(r"from\s+dlt\.sources\.rest_api\s+import", transform_src))
    has_rest_call = "rest_api_resources(" in transform_src or "rest_api_source(" in transform_src
    if not (has_rest_import and has_rest_call):
        return False, "no dlt.sources.rest_api import / rest_api_resources(...) call found"
    return True, ""


def resolve_result_col(checks_cols: list[str]) -> str | None:
    """The landed scalar status column, whatever spelling the closure produced.

    dlt's snake_case naming convention uses ``__`` as its PATH SEPARATOR, so a
    payload nesting ``{"result": {"status": ...}}`` lands as ``result__status``
    — double underscore. An earlier version of this checker accepted only
    ``result_status`` (single), which dlt never emits, so the flatten check was
    unsatisfiable on the taught path and failed identically on every arm
    including the no-skills baseline.

    Shared deliberately between the flatten check and the tri-state check. They
    were two independent lookups keyed off the same tuple, so one wrong spelling
    failed both — and the tri-state failure read as a boolean coercion that had
    never happened. One resolver means a lookup miss can no longer masquerade as
    a second, unrelated defect.
    """
    for c in checks_cols:
        low = c.lower()
        if low in ("result", "status") or re.fullmatch(r"result_{1,2}status", low):
            return c
    return None


def no_hardcoded_base_url_or_path(transform_src: str) -> tuple[bool, str]:
    if "127.0.0.1" in transform_src or "localhost" in transform_src:
        return False, "transform hardcodes the stub host instead of reading secrets['base_url']"
    if "/v1/checks" in transform_src or "/v1/monitors" in transform_src:
        return False, ("transform hardcodes an endpoint path instead of reading "
                       "secrets['endpoint_<model>']")
    return True, ""


# ---------------------------------------------------------------------------
# Live re-materialization: run the closure's OWN transform against a fresh
# stub instance, exactly as the agent's copy did against the runner's.
# ---------------------------------------------------------------------------

_MATERIALIZE_HARNESS = '''
import sys, types
from dataclasses import dataclass, field
from pathlib import Path

@dataclass
class DuckDbOutput:
    path: str; schema: str; model_tables: dict; models: dict = field(default_factory=dict)

nxd = types.ModuleType("nxd"); core = types.ModuleType("nxd.core")
ctx = types.ModuleType("nxd.core.context"); ctx.DuckDbOutput = DuckDbOutput
dp = types.SimpleNamespace(on_transform=lambda *a, **k: (lambda fn: fn), main=lambda: None)
nxd.data_product, nxd.core, core.context = dp, core, ctx
sys.modules.update({"nxd": nxd, "nxd.core": core, "nxd.core.context": ctx})

sys.path.insert(0, ".")
from transform.main import PHYSICAL_MODELS, ingest

out = DuckDbOutput(path=sys.argv[1], schema="main",
                   model_tables={m: m for m in PHYSICAL_MODELS})
# The supervisor merges every service in `.secrets([...])` into ONE flat map
# keyed by the raw attribute key (local_python_compute.rs: prepare_execution_context
# flat_maps each handler's values into a single serde_json::Map). Passing a
# nested {"api_source": ...} here would grade the wrong contract.
secrets = {"base_url": sys.argv[2], "auth_type": "bearer", "auth_token": sys.argv[3]}
ingest(duckdb=out, secrets=secrets)
'''

_UNINSTALLABLE_PREFIXES = ("nxd",)


def closure_requirements(root: Path) -> list[str]:
    req = root / "requirements.txt"
    if not req.is_file():
        return []
    specs = []
    for raw in req.read_text(encoding="utf-8").splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line or line.startswith("-"):
            continue
        name = re.split(r"[\[<>=!~ ]", line, maxsplit=1)[0].strip().lower()
        if name.startswith(_UNINSTALLABLE_PREFIXES):
            continue
        specs.append(line)
    return specs


def materialize_closure(root: Path, base_url: str, token: str) -> tuple[Path | None, str]:
    try:
        import duckdb  # noqa: F401, PLC0415
    except ImportError:
        return None, "duckdb not importable in checker env"

    scratch = Path(tempfile.mkdtemp(prefix="api-source-closure-check-"))
    db = scratch / "data.duckdb"
    harness = scratch / "_materialize.py"
    harness.write_text(_MATERIALIZE_HARNESS, encoding="utf-8")

    cmd = ["uv", "run", "--no-project"]
    for spec in closure_requirements(root):
        cmd += ["--with", spec]
    cmd += ["python", str(harness), str(db), base_url, token]
    try:
        proc = subprocess.run(
            cmd, cwd=str(root), capture_output=True, text=True,
            timeout=MATERIALIZE_TIMEOUT_S,
            env={**os.environ, "PYTHONPATH": ""},
        )
    except subprocess.TimeoutExpired:
        return None, f"transform timed out after {MATERIALIZE_TIMEOUT_S}s"
    except OSError as exc:
        return None, f"transform failed to start: {exc}"

    if proc.returncode != 0:
        tail = (proc.stderr or proc.stdout).strip().splitlines()
        return None, f"transform failed: {tail[-1] if tail else 'no output'}"
    if not db.is_file():
        return None, "transform ran but wrote no database"
    return db, ""


def tables_in(db: Path) -> list[str]:
    import duckdb  # noqa: PLC0415

    con = duckdb.connect(str(db), read_only=True)
    return [r[0] for r in con.execute("SHOW TABLES").fetchall()]


def col_names(db: Path, table: str) -> list[str]:
    import duckdb  # noqa: PLC0415

    con = duckdb.connect(str(db), read_only=True)
    return [r[1] for r in con.execute(f"PRAGMA table_info('{table}')").fetchall()]


def rowcount(db: Path, table: str) -> int:
    import duckdb  # noqa: PLC0415

    con = duckdb.connect(str(db), read_only=True)
    return con.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]


ENDPOINT_PREFIX = "endpoint_"


def declared_endpoints(root: Path) -> dict[str, str]:
    """The closure's endpoint map, as {model name: endpoint path}.

    Read from infra-profile.yaml's `endpoint_<model>` attributes. An earlier
    revision of the api-source skill had the closure write an
    `api-source-endpoints` companion file instead; that channel is gone, and
    reading it here would silently pass a closure built to the retired contract.

    The label-prefixed multi-source spelling (`orders_endpoint_checks`) is
    matched too -- this scenario is single-source, but a checker that only
    recognized the unlabeled form would report a correct labeled closure as
    having declared nothing and fall through to the substring heuristic.
    """
    fields, _ = profile_attributes(root)
    mapping: dict[str, str] = {}
    for key, value in fields.items():
        # partition() returns an empty tail for a key that does not contain the
        # prefix at all, so the emptiness check covers both "not an endpoint
        # attribute" and the degenerate key named exactly `endpoint_`.
        _, _, model = key.partition(ENDPOINT_PREFIX)
        if model and value:
            mapping[model] = value
    return mapping


def declared_models(root: Path) -> dict[str, str]:
    """The endpoint map inverted: {endpoint path: model name}."""
    return {path: model for model, path in declared_endpoints(root).items()}


def endpoints_not_public(root: Path) -> list[str]:
    """Endpoint attribute keys that will NOT survive an export.

    Asserts the POSITIVE. Export redaction is fail-closed: the supervisor keeps
    an attribute's value only when it carries `public: true` literally
    (`export.rs` compares against `Some(Bool(true))`), so an attribute with no
    `public:` line at all is stripped exactly like `public: false`. A scan for
    an explicit "false" would miss that case -- and the omitted flag is the more
    likely authoring slip of the two.
    """
    fields, public_flags = profile_attributes(root)
    return sorted(
        key for key in fields
        if ENDPOINT_PREFIX in key and public_flags.get(key) != "true"
    )


def find_table(tables: list[str], hint: str, other_hint: str | None = None) -> str | None:
    """Fallback resolution when the profile declares no usable endpoint map.

    Substring-first resolution collides whenever a derived model happens to
    contain BOTH hints (e.g. `check_monitor_resolution` matches "monitor" and
    "check", and sorts ahead of both `checks` and `monitors`) — the checker then
    silently measures one table as if it were the other. Prefer an exact name or
    plural match over the whole table set, drop dlt bookkeeping tables, exclude
    candidates that also carry the other hint, and report ambiguity loudly
    instead of taking whatever sorts first.
    """
    candidates = [t for t in tables if not t.lower().startswith("_dlt")]
    for exact in (hint, hint + "s"):
        hit = next((t for t in candidates if t.lower() == exact), None)
        if hit:
            return hit
    subset = [t for t in candidates if hint in t.lower()]
    if other_hint:
        narrowed = [t for t in subset if other_hint not in t.lower()]
        if narrowed:
            subset = narrowed
    if len(subset) > 1:
        FAILURES.append(
            f"landed:table-resolution-ambiguous: hint {hint!r} matches "
            f"{sorted(subset)} — cannot decide which table to measure"
        )
        return None
    return subset[0] if subset else None


def resolve_table(root: Path, tables: list[str], endpoint: str, hint: str,
                  other_hint: str) -> tuple[str | None, str]:
    """Resolve the table backing `endpoint` by the model name the closure itself
    declared, falling back to the hardened substring heuristic."""
    model = declared_models(root).get(endpoint)
    if model:
        hit = next((t for t in tables if t.lower() == model.lower()), None)
        if hit:
            return hit, ""
        return None, (f"infra-profile.yaml declares endpoint_{model} = {endpoint}, "
                      f"but no table named {model!r} landed; tables were {tables}")
    return find_table(tables, hint, other_hint), str(tables)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--fixtures", required=True, type=Path)
    ap.add_argument("--root", default=Path("."), type=Path)
    args = ap.parse_args()

    root: Path = args.root
    fixtures: Path = args.fixtures

    # The closure does NOT necessarily land at the workspace root. nxd-run-job-loop
    # documents `…/nxd-jobs/<workflow>/closure/` (SKILL.md "Author dp-spec.md"),
    # with the IR beside it — so an agent following the skill correctly writes
    # transform/main.py several directories down. A checker hardcoding
    # `<root>/transform/main.py` fails a correct closure and reports it as a
    # missing one, which is worse than not checking: it is a false accusation
    # aimed at the agent rather than at the checker.
    #
    # Resolve by SEARCH, anchored on the file that defines a closure. Prefer the
    # workspace root when it is itself a closure (the flat layout other scenarios
    # use), else take the shallowest match so a nested scratch copy cannot win
    # over the real one.
    def _find_closure(base: Path) -> Path:
        if (base / "transform" / "main.py").is_file():
            return base
        found = sorted(
            (p.parent.parent for p in base.rglob("transform/main.py")),
            key=lambda p: (len(p.relative_to(base).parts), str(p)),
        )
        return found[0] if found else base

    root = _find_closure(root)

    # ---- structural: closure exists -------------------------------------
    transform_path = root / "transform" / "main.py"
    if not check("closure:transform-exists", transform_path.is_file(), str(transform_path)):
        print_report()
        return 1
    transform_src = transform_path.read_text(encoding="utf-8")

    for rel in ("spec.py", "models.py", "infra-profile.yaml", "requirements.txt"):
        check(f"closure:{rel}", (root / rel).is_file())
    endpoints = declared_endpoints(root)
    check(
        "closure:endpoints-in-profile",
        bool(endpoints),
        "no endpoint_<model> attributes in infra-profile.yaml — the endpoint map "
        "belongs on the api-source service, one attribute per model, not in a "
        "companion file beside the transform",
    )
    # An endpoint path is topology, not a credential. Stripped from an export,
    # the recipient gets a closure that cannot run until they work out what the
    # paths were -- a silent failure at their end, not the sender's, so nothing
    # here would otherwise catch it.
    non_public = endpoints_not_public(root)
    check(
        "closure:endpoints-public",
        not non_public,
        f"{non_public} not marked public: true — an endpoint path is non-secret "
        f"topology and must survive export; redaction is fail-closed, so an "
        f"omitted public: flag strips it just as public: false does",
    )
    check(
        "closure:no-endpoints-companion",
        not (root / "api-source-endpoints").is_file(),
        "closure still ships an api-source-endpoints companion file; the endpoint "
        "map moved to infra-profile.yaml attributes",
    )

    # ---- credential handling ----------------------------------------------
    ok, detail = no_literal_secret_in_source(root)
    check("secret:not-a-literal-in-source", ok, detail)

    ok, detail, fields = infra_profile_has_structured_auth(root)
    check("secret:structured-auth-in-profile", ok, detail)

    ok, detail = sensitivity_artifacts_present(root)
    check("secret:sensitivity-artifacts-present", ok, detail)

    # ---- ingestion mechanism ------------------------------------------------
    ok, detail = auth_is_dispatched_on_auth_type(transform_src)
    check("secret:auth-dispatched-on-auth-type", ok, detail)

    ok, detail = uses_rest_api_resources(transform_src)
    check("ingestion:rest-api-resources-used", ok, detail)

    ok, detail = no_hardcoded_base_url_or_path(transform_src)
    check("ingestion:no-hardcoded-url-or-path", ok, detail)

    # ---- live re-materialization: does it actually work end-to-end? --------
    stub = load_stub(fixtures)
    server, port, thread = stub.start_server()
    base_url = f"http://127.0.0.1:{port}"
    try:
        # Confirm the STUB itself behaves as documented before blaming the
        # closure for anything: unauthenticated must 401, authenticated must
        # 200. This isolates "the fixture is broken" from "the closure is
        # wrong" in the failure output.
        try:
            urllib.request.urlopen(
                urllib.request.Request(f"{base_url}/v1/monitors"), timeout=5
            )
            fixture_ok = False
        except urllib.error.HTTPError as exc:
            fixture_ok = exc.code == 401
        if not check("fixture:stub-enforces-auth", fixture_ok,
                      "stub did not 401 an unauthenticated request"):
            print_report()
            return 1

        db, why = materialize_closure(root, base_url, stub.VALID_TOKEN)
        if db is None:
            check("closure:materializes", False, why)
            # A closure that never even calls the endpoint cannot be
            # distinguished from one that used the wrong token by this
            # failure alone, so also probe directly: replay a request with
            # the WRONG token to make sure the checker's own harness isn't
            # the reason nothing landed.
            print_report()
            return 1
        check("closure:materializes", True)

        tables = tables_in(db)
        monitors_table, monitors_detail = resolve_table(
            root, tables, "/v1/monitors", "monitor", "check")
        checks_table, checks_detail = resolve_table(
            root, tables, "/v1/checks", "check", "monitor")
        check("landed:monitors-table-present", monitors_table is not None, monitors_detail)
        check("landed:checks-table-present", checks_table is not None, checks_detail)
        if not (monitors_table and checks_table):
            print_report()
            return 1

        # ---- pagination: all 12 monitors and all 37 checks must land -----
        n_monitors = rowcount(db, monitors_table)
        n_checks = rowcount(db, checks_table)
        check(
            "landed:pagination-monitors-complete",
            n_monitors == 12,
            f"landed {n_monitors} monitor rows, expected 12 (default page size is "
            f"10 — an unconfigured single fetch lands a truncated slice with no error)",
        )
        check(
            "landed:pagination-checks-complete",
            n_checks == 37,
            f"landed {n_checks} check rows, expected 37 (same truncation trap)",
        )

        # ---- nested field flattened: result must be a flat scalar column --
        checks_cols = col_names(db, checks_table)
        result_col = resolve_result_col(checks_cols)
        has_flat_result_col = result_col is not None
        # dlt names a spawned child table with its PATH SEPARATOR: `checks__result`,
        # double underscore. A bare `startswith(checks_table)` also matches the
        # closure's own derived models — `checks_enriched` is a legitimate model
        # this very scenario's questions invite, and reading it as evidence of an
        # unflattened payload punishes the agent for doing the task.
        has_child_table = any(
            t.lower().startswith(checks_table.lower() + "__") for t in tables
        )
        check(
            "landed:nested-result-flattened",
            has_flat_result_col and not has_child_table,
            f"checks columns were {checks_cols}, tables were {tables} — the payload "
            f"nests {{'result': {{'status': ..., 'latency_ms': ...}}}}; a scalar "
            f"status column must be flattened before landing, not left as a nested "
            f"dict (which dlt would otherwise spawn a parent__result child table for)",
        )

        # ---- tri-state result column: 'unknown' must survive, not fold into
        # a boolean up/down -----------------------------------------------
        import duckdb  # noqa: PLC0415

        con = duckdb.connect(str(db), read_only=True)
        distinct_results = set()
        if result_col:
            distinct_results = {
                r[0] for r in con.execute(
                    f'SELECT DISTINCT "{result_col}" FROM "{checks_table}"'
                ).fetchall()
            }
        check(
            "landed:tri-state-result-preserved",
            {"unknown", "up", "down"} <= {str(v).lower() for v in distinct_results},
            # When no column resolved, say so instead of reporting an empty
            # distinct set: "values were set()" reads as a coercion the closure
            # performed, which accuses the agent of a defect that never happened.
            (
                f"no scalar status column among {checks_cols} — the flatten check "
                f"above explains why; this check could not run"
                if result_col is None else
                f"distinct {result_col!r} values were {distinct_results} — expected "
                f"up/down/unknown all present; a boolean coercion silently folds "
                f"'unknown' (an inconclusive probe) into 'down'"
            ),
        )

        # ---- orphaned monitor_id rows must be visible, not silently dropped
        # by an inner join --------------------------------------------------
        monitor_cols = col_names(db, monitors_table)
        # Exact match only: a substring test grabs `check_id`, `_dlt_id` or
        # `_dlt_load_id` on plenty of plausible schemas and then compares the
        # wrong key space against the checks table.
        monitor_id_col = next(
            (c for c in monitor_cols if c.lower() in ("id", "monitor_id")), None)
        checks_monitor_id_col = next((c for c in checks_cols if "monitor" in c.lower() and "id" in c.lower()), None)
        orphan_visible = False
        orphan_detail = "could not identify a monitor-id column on both tables"
        if monitor_id_col and checks_monitor_id_col:
            landed_monitor_ids = {
                r[0] for r in con.execute(f'SELECT "{monitor_id_col}" FROM "{monitors_table}"').fetchall()
            }
            landed_check_monitor_ids = {
                r[0] for r in con.execute(f'SELECT DISTINCT "{checks_monitor_id_col}" FROM "{checks_table}"').fetchall()
            }
            orphans = landed_check_monitor_ids - landed_monitor_ids
            # Either an inner-joined derived model that still leaves the 4
            # orphan rows independently queryable from the raw checks table,
            # or a landed flag column naming them, counts. The failure mode
            # this guards is the 4 rows vanishing everywhere.
            orphan_visible = bool(orphans) or any(
                "orphan" in c.lower() or "missing_monitor" in c.lower() or "unmatched" in c.lower()
                for t in tables for c in col_names(db, t)
            )
            orphan_detail = (
                f"raw checks table retains monitor_ids {sorted(orphans)} not present "
                f"in monitors (visible), or no orphan/unmatched flag column found "
                f"anywhere — 4 rows (ids 9101-9104) reference a monitor that was "
                f"never in /v1/monitors and must stay visible per the brief"
            )
        check("landed:orphan-monitor-checks-visible", orphan_visible, orphan_detail)

        # ---- monitor with zero checks (1006) must still be enumerable -----
        never_polled_id = 1006
        never_polled_present = False
        if monitor_id_col:
            never_polled_present = any(
                r[0] in (1006, "1006") for r in con.execute(
                    f'SELECT "{monitor_id_col}" FROM "{monitors_table}"'
                ).fetchall()
            )
        check(
            "landed:never-polled-monitor-enumerable",
            never_polled_present,
            f"monitor {never_polled_id} (legacy-webhook-relay, zero checks ever run) "
            f"must still appear in the landed monitors table",
        )

    finally:
        stub.stop_server(server, thread)

    print_report()
    return 1 if FAILURES else 0


if __name__ == "__main__":
    sys.exit(main())

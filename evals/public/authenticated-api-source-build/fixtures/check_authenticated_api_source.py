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

# The api-source architecture gate lives in one place and is imported by every
# REST scenario's checker -- see evals/tools/api_connector_gate.py for why a
# second copy is worse than a shared import. Path-based because this file runs
# under `uv run --no-project` from an arbitrary cwd.
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "tools"))
from api_connector_gate import (  # noqa: E402
    ENDPOINT_PREFIX,
    declared_endpoints,
    endpoint_secrets,
    endpoints_not_public,
    find_closure,
    no_hardcoded_url_or_path,
    profile_has_structured_auth,
    profile_attributes,
    transform_sources,
    uses_rest_api_resources,
)
from api_connector_gate import (  # noqa: E402
    headers_built_from_secrets as gate_headers_built_from_secrets,
)

# The stub's own host and the two endpoint paths the brief names. A closure
# reading `secrets["base_url"]` and `secrets["endpoint_<model>"]` carries
# neither as a literal.
STUB_HOSTS = ("127.0.0.1", "localhost")
STUB_PATHS = ("/v1/checks", "/v1/monitors")

FAILURES: list[str] = []
PASSES: list[str] = []

MATERIALIZE_TIMEOUT_S = 300
ENVELOPE_METADATA_COLUMNS = frozenset({"page", "per_page", "total", "pages"})
ENVELOPE_FACT = "landed:envelope-metadata-absent"
VALID_TOKEN = "bcn_live_9f3ac2e7d84b41f0a6c5d2e19b7f0033"
# Mirrors stub_beacon_api.REQUIRED_USER_AGENT. Duplicated the same way
# VALID_TOKEN is, so the static checks can run before the stub is loaded;
# check_stub_constants_match() below pins the two together so a drift in one
# fails loudly instead of silently disabling a check.
REQUIRED_USER_AGENT = "nexty-test-client/1.0"


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


def header_declared_in_profile(root: Path) -> tuple[bool, str]:
    """The required User-Agent must live in the profile as a `header_*`
    attribute, not in the transform source.

    Per api-source.md's "Custom request headers": one flat attribute per
    header, `header_<name>` with `-` written as `_`. The header name is
    case-insensitive (RFC 7230 §3.2) and so is its encoding here, so accept any
    case for the KEY — but the VALUE must match exactly, since that string is
    what the upstream matches on.
    """
    profile = root / "infra-profile.yaml"
    if not profile.is_file():
        return False, "infra-profile.yaml missing"
    fields, _ = profile_attributes(root)
    matches = [k for k in fields if k.lower() == "header_user_agent"]
    if not matches:
        declared = sorted(k for k in fields if k.lower().startswith("header_"))
        if declared:
            return False, (f"no header_user_agent attribute; found {declared} — the "
                           f"required header is User-Agent")
        return False, ("no header_user_agent attribute in the api-source service; the "
                       "API requires User-Agent and it must come from the profile, "
                       "not from a literal in the transform")
    got = fields[matches[0]]
    if got != REQUIRED_USER_AGENT:
        return False, (f"header_user_agent is {got!r}, but the API requires "
                       f"{REQUIRED_USER_AGENT!r}")
    return True, ""


def header_marked_public(root: Path) -> tuple[bool, str]:
    """A non-secret header is `public: true` so it survives an export.

    Separate from `header_declared_in_profile` on purpose: a header marked
    `public: false` still WORKS (the transform reads every attribute
    regardless), it just gets redacted out of an export and the recipient has
    to rediscover it. That is a defect in the export contract, not in
    ingestion, and merging the two would report it as a broken header.
    """
    _, public_flags = profile_attributes(root)
    for key, flag in public_flags.items():
        if key.lower() != "header_user_agent":
            continue
        if flag == "true":
            return True, ""
        return False, (f"header_user_agent is public: {flag} — a non-secret header "
                       f"should be public: true so it survives export_data_product")
    return False, "header_user_agent carries no public: flag"


def headers_built_from_secrets(root: Path) -> tuple[bool, str]:
    """This scenario's header value, through the shared implementation."""
    return gate_headers_built_from_secrets(root, REQUIRED_USER_AGENT)


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


def envelope_metadata_columns(columns: list[str]) -> list[str]:
    """Return pagination-envelope keys that leaked into a landed row table.

    A correct dlt ``data_selector`` (or an equivalent pre-landing mapping)
    removes the response envelope before rows reach DuckDB. Keep this helper
    independent of DuckDB so the evaluator can pin the landed-column contract
    without relying on transcript narration.
    """
    return sorted(
        {column for column in columns if column.casefold() in ENVELOPE_METADATA_COLUMNS},
        key=str.casefold,
    )


# ---------------------------------------------------------------------------
# Live re-materialization: run the closure's OWN transform against a fresh
# stub instance, exactly as the agent's copy did against the runner's.
# ---------------------------------------------------------------------------

_MATERIALIZE_HARNESS = '''
import json, sys, types
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
# The endpoint map arrives the same way -- one `endpoint_<model>` attribute per
# API-backed model, flattened into the very same map. Withholding it here while
# the checker separately forbids a hardcoded endpoint path would leave the
# closure no legal source for the path at all: a correct transform would raise
# KeyError and be reported as a broken closure.
#
# `header_user_agent` rides the same channel for the same reason. A closure that
# hardcodes the User-Agent instead still passes THIS harness (it sends the right
# header either way); what catches that is the static `header:built-from-secrets`
# check. A closure that ignores headers entirely fails here, because the stub
# 403s it before it can authenticate.
secrets.update(json.loads(sys.argv[4]))
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


def materialize_closure(
    root: Path, base_url: str, token: str, extra_secrets: dict[str, str]
) -> tuple[Path | None, str]:
    """Run the closure's own transform against a live stub.

    `extra_secrets` carries every flat attribute beyond base_url/auth that the
    supervisor would have merged in -- the `endpoint_<model>` paths and the
    `header_*` request headers -- because the checker forbids hardcoding either
    and a correct transform must therefore have some legal source for both.
    """
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
    cmd += ["python", str(harness), str(db), base_url, token, json.dumps(extra_secrets)]
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


def declared_models(root: Path) -> dict[str, str]:
    """The endpoint map inverted: {endpoint path: model name}."""
    return {path: model for model, path in declared_endpoints(root).items()}



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

    # The closure does NOT necessarily land at the workspace root — see
    # find_closure() in api_connector_gate for why this is a search rather than
    # a fixed path.
    root = find_closure(root)

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

    ok, detail, fields = profile_has_structured_auth(
        root, expected_token=VALID_TOKEN
    )
    check("secret:structured-auth-in-profile", ok, detail)

    ok, detail = sensitivity_artifacts_present(root)
    check("secret:sensitivity-artifacts-present", ok, detail)

    # ---- custom client header (NEX-873) -----------------------------------
    ok, detail = header_declared_in_profile(root)
    check("header:declared-in-profile", ok, detail)

    ok, detail = header_marked_public(root)
    check("header:non-secret-marked-public", ok, detail)

    ok, detail = headers_built_from_secrets(root)
    check("header:built-from-secrets", ok, detail)

    # ---- ingestion mechanism ------------------------------------------------
    ok, detail = auth_is_dispatched_on_auth_type(transform_src)
    check("secret:auth-dispatched-on-auth-type", ok, detail)

    ok, detail = uses_rest_api_resources(root)
    check("ingestion:rest-api-resources-used", ok, detail)

    ok, detail = no_hardcoded_url_or_path(root, STUB_HOSTS, STUB_PATHS)
    check("ingestion:no-hardcoded-url-or-path", ok, detail)

    # ---- live re-materialization: does it actually work end-to-end? --------
    stub = load_stub(fixtures)
    # The static checks above compare against this module's own copies of the
    # token and User-Agent. If the stub's values drift from them, those checks
    # start grading a string the fixture no longer serves — passing or failing
    # for reasons unrelated to the closure. Fail loudly here instead.
    if not check("fixture:constants-match-stub",
                 (VALID_TOKEN, REQUIRED_USER_AGENT)
                 == (stub.VALID_TOKEN, stub.REQUIRED_USER_AGENT),
                 "checker constants drifted from stub_beacon_api.py"):
        print_report()
        return 1
    server, port, thread = stub.start_server()
    base_url = f"http://127.0.0.1:{port}"
    try:
        # Confirm the STUB itself behaves as documented before blaming the
        # closure for anything. This isolates "the fixture is broken" from "the
        # closure is wrong" in the failure output. Two gates, probed
        # separately because they fail for different reasons:
        #
        #   no User-Agent            -> 403 (header gate, checked FIRST)
        #   right UA, no/wrong token -> 401 (credential gate)
        #
        # Probing auth requires sending the required UA, since otherwise the
        # header gate answers first and the auth gate is never reached.
        def _probe(headers: dict) -> int | None:
            """Status of a GET /v1/monitors, or None if it unexpectedly succeeded."""
            try:
                urllib.request.urlopen(
                    urllib.request.Request(f"{base_url}/v1/monitors", headers=headers),
                    timeout=5,
                )
                return None
            except urllib.error.HTTPError as exc:
                return exc.code

        # urllib sends its own User-Agent by default, which is precisely a
        # client the stub does not recognize — so an empty header dict is a
        # faithful "wrong UA" probe.
        if not check("fixture:stub-enforces-header", _probe({}) == 403,
                     "stub did not 403 a request with an unrecognized User-Agent"):
            print_report()
            return 1
        if not check("fixture:stub-enforces-auth",
                     _probe({"User-Agent": stub.REQUIRED_USER_AGENT}) == 401,
                     "stub did not 401 an unauthenticated request"):
            print_report()
            return 1

        # Drop the probes' own traffic so the wire assertion below measures
        # only what the CLOSURE sent.
        stub.reset_observations()

        extra_secrets = dict(endpoint_secrets(root))
        extra_secrets["header_user_agent"] = stub.REQUIRED_USER_AGENT
        db, why = materialize_closure(
            root, base_url, stub.VALID_TOKEN, extra_secrets)
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

        # The header actually reached the outbound request. Materializing at
        # all already implies it — the stub 403s anything else — but assert it
        # against observed traffic anyway: if the gate is ever weakened, this
        # keeps failing instead of quietly passing on a closure that never
        # sent the header.
        seen = stub.observations()
        wire_ok = any(ua == stub.REQUIRED_USER_AGENT and authorized
                      for _, ua, authorized in seen)
        distinct = sorted({ua for _, ua, _ in seen})
        check("header:reaches-outbound-request", wire_ok,
              f"no authorized request arrived carrying {stub.REQUIRED_USER_AGENT!r}; "
              f"User-Agents observed: {distinct}")

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

        # ---- response envelope must not land as row data -----------------
        envelope_columns = {
            table: envelope_metadata_columns(col_names(db, table))
            for table in (monitors_table, checks_table)
        }
        leaked = {table: columns for table, columns in envelope_columns.items() if columns}
        check(
            ENVELOPE_FACT,
            not leaked,
            f"pagination metadata leaked into landed row tables: {leaked}; "
            "the landed row tables must not carry the response envelope metadata",
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

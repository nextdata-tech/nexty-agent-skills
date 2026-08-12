"""The api-source architecture gate, shared by every REST scenario's checker.

One implementation, imported by both `authenticated-api-source-build` and
`worldbank-live`. The gate answers three questions about a landed closure, all
decidable from disk with no network and no supervisor:

1. does ingestion go through dlt's REST connector, and ONLY through it
   (`uses_rest_api_resources`);
2. is the endpoint topology declared in `infra-profile.yaml` rather than a
   retired companion file (`declared_endpoints` / `endpoints_not_public`);
3. is the deployment-varying part — host, endpoint path — read from `secrets`
   rather than frozen into the transform (`no_hardcoded_url_or_path`).

Why shared rather than copied: NEX-873 tightened `uses_rest_api_resources` from
presence-only to hybrid-rejecting after the measured benchmark
(`evals/benchmarks/entries/2026-08-11-api-source-custom-client-headers.md`)
found agents importing `rest_api_resources` while `requests` fetched the rows
beside it. That tightening landed in one scenario's checker. A second copy is a
second thing to tighten, and the copy that gets missed is the one that keeps
passing hand-rolled closures — which reads as "this scenario has a connector
gate" while it grades nothing.

Checkers reach this module by path, since they run under `uv run --no-project`
from an arbitrary cwd:

    sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "tools"))
    from api_connector_gate import uses_rest_api_resources
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

ENDPOINT_PREFIX = "endpoint_"


# ---------------------------------------------------------------------------
# Locating the closure and its sources
# ---------------------------------------------------------------------------


def find_closure(base: Path) -> Path:
    """The closure root under `base`, which is not necessarily `base` itself.

    `nxd-run-job-loop` documents `…/nxd-jobs/<workflow>/closure/` (SKILL.md
    "Author dp-spec.md"), with the IR beside it — so an agent following the
    skill correctly writes `transform/main.py` several directories down. A
    checker hardcoding `<root>/transform/main.py` fails a correct closure and
    reports it as a missing one, which is worse than not checking: it is a
    false accusation aimed at the agent rather than at the checker.

    Prefer `base` when it is itself a closure (the flat layout some scenarios
    use), else take the shallowest match so a nested scratch copy cannot win
    over the real one.
    """
    if (base / "transform" / "main.py").is_file():
        return base
    found = sorted(
        (p.parent.parent for p in base.rglob("transform/main.py")),
        key=lambda p: (len(p.relative_to(base).parts), str(p)),
    )
    return found[0] if found else base


def transform_sources(root: Path) -> list[Path]:
    """Every `transform/*.py`, sorted.

    Every scan in this module covers the whole directory rather than `main.py`
    alone: with only `main.py` checked, moving a fetch loop into a sibling
    module defeats the gate without changing the architecture at all.
    """
    transform_dir = root / "transform"
    if not transform_dir.is_dir():
        return []
    return sorted(transform_dir.glob("*.py"))


# ---------------------------------------------------------------------------
# infra-profile.yaml attributes
# ---------------------------------------------------------------------------


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

    Shared by the auth, endpoint and header checks so a profile that fails one
    is still fully parsed for the others. Folding this back into any single
    caller re-creates the bug it was extracted to kill: an early bail on a
    missing auth_token also empties the header check's input, which then
    reports a present-and-correct header as absent -- one defect surfacing as
    two, with the second aimed at the wrong file.
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


def declared_endpoints(root: Path) -> dict[str, str]:
    """The closure's endpoint map, as {model name: endpoint path}.

    Read from infra-profile.yaml's `endpoint_<model>` attributes. An earlier
    revision of the api-source skill had the closure write an
    `api-source-endpoints` companion file instead; that channel is gone, and
    reading it here would silently pass a closure built to the retired
    contract.

    The label-prefixed multi-source spelling (`orders_endpoint_checks`) is
    matched too -- a checker that only recognized the unlabeled form would
    report a correct labeled closure as having declared nothing.
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


def endpoint_secrets(root: Path) -> dict[str, str]:
    """The endpoint attributes as the transform will see them in `secrets`.

    Keyed by the RAW profile key, not by the model name `declared_endpoints`
    parses out: the label-prefixed multi-source spelling
    (`orders_endpoint_checks`) reaches the transform under that full key, and
    rebuilding it as `endpoint_<model>` would hand a correct labeled closure a
    key it never asked for while withholding the one it did.
    """
    fields, _ = profile_attributes(root)
    return {
        key: value for key, value in fields.items()
        if ENDPOINT_PREFIX in key and value
    }


# ---------------------------------------------------------------------------
# AST helpers
# ---------------------------------------------------------------------------


def docstring_nodes(tree: ast.Module) -> set[int]:
    """id()s of the Constant nodes that are docstrings, not code."""
    out: set[int] = set()
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef,
                                 ast.ClassDef)):
            continue
        body = getattr(node, "body", None)
        if (body and isinstance(body[0], ast.Expr)
                and isinstance(body[0].value, ast.Constant)
                and isinstance(body[0].value.value, str)):
            out.add(id(body[0].value))
    return out


def string_literals(tree: ast.Module) -> list[str]:
    """Every string literal that is real code, docstrings excluded."""
    skip = docstring_nodes(tree)
    return [n.value for n in ast.walk(tree)
            if isinstance(n, ast.Constant) and isinstance(n.value, str)
            and id(n) not in skip]


def _dotted(node: ast.AST) -> str:
    """`requests.Session` for an Attribute chain, `urlopen` for a bare Name."""
    parts: list[str] = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
    else:
        return ""
    return ".".join(reversed(parts))


# ---------------------------------------------------------------------------
# The connector gate
# ---------------------------------------------------------------------------

# Modules whose presence in a transform means the closure is fetching HTTP
# itself. `urllib.request` and `http.client` are stdlib, the rest are the usual
# third-party clients; `dlt.sources.helpers.requests` is dlt's OWN requests
# wrapper, which is still a hand-rolled loop -- dlt-flavored, but not the REST
# connector, and it lands rows through a plain generator exactly the same way.
_HTTP_CLIENT_MODULES = (
    "requests", "httpx", "aiohttp", "urllib3", "httplib2",
    "urllib.request", "urllib.error", "http.client",
    # dlt's own requests wrapper -- see above.
    "dlt.sources.helpers.requests",
)


def _is_http_module(path: str) -> bool:
    """True when a resolved dotted path lies inside an HTTP client module."""
    return any(path == m or path.startswith(f"{m}.") for m in _HTTP_CLIENT_MODULES)


def _http_client_calls(tree: ast.Module) -> list[str]:
    """Hand-rolled HTTP calls in one module, resolved through import aliases.

    AST rather than substring search on purpose: `api-source.md` discusses
    `requests` and `urllib` in prose, and a closure that quotes that guidance in
    a docstring or comment must not be failed for describing the thing it
    correctly avoided.

    Resolution is on the FULL dotted path, not the bound root name. `import
    urllib` binds the root `urllib`, under which `urllib.request.urlopen` is a
    network call and `urllib.parse.quote` is string manipulation -- so keying on
    the root flags a correct closure for quoting a URL path. This repo already
    refuses to make that trade in the self-check's own transport scan
    (`reference/self-check.md`: "`urllib` would also catch `urllib.parse`, which
    is pure string manipulation with no network and is used by shipped example
    transforms"), and a rule that fires on correct closures gets deleted rather
    than obeyed. Resolving the whole path keeps `urllib.request` denied and
    `urllib.parse` free.
    """
    aliases: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                # `import urllib.request` binds the root `urllib`, but the alias
                # maps to the root MODULE so a later `.request.urlopen` resolves
                # back to the full path. `import x as y` binds y to all of x.
                if a.asname:
                    aliases[a.asname] = a.name
                else:
                    root = a.name.split(".")[0]
                    aliases.setdefault(root, root)
        elif isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            for a in node.names:
                aliases[a.asname or a.name] = f"{mod}.{a.name}" if mod else a.name
    hits: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        name = _dotted(node.func)
        if not name:
            continue
        root, _, rest = name.partition(".")
        if root not in aliases:
            continue
        resolved = aliases[root] + (f".{rest}" if rest else "")
        if _is_http_module(resolved):
            hits.add(name)
    return sorted(hits)


def _uses_dlt_rest(tree: ast.Module) -> bool:
    """A `dlt.sources.rest_api` import AND a real call to its entry points."""
    imported = any(
        isinstance(n, ast.ImportFrom) and (n.module or "").startswith("dlt.sources.rest_api")
        for n in ast.walk(tree)
    )
    called = any(
        isinstance(n, ast.Call)
        and _dotted(n.func).split(".")[-1] in ("rest_api_resources", "rest_api_source")
        for n in ast.walk(tree)
    )
    return imported and called


def uses_rest_api_resources(root: Path) -> tuple[bool, str]:
    """Ingestion goes through dlt's REST connector -- and ONLY through it.

    Two halves, because a closure can fail either independently:

    1. the dlt REST connector is actually used, and
    2. nothing fetches HTTP beside it.

    The second half is the one that matters in practice. Checking only the
    first made this fact presence-only: a closure could import
    `rest_api_resources`, never reach the wire with it, and hand-roll a
    `requests` loop next to it -- passing a check whose entire purpose is to
    require the connector architecture. The measured NEX-873 benchmark
    (`evals/benchmarks/entries/2026-08-11-api-source-custom-client-headers.md`)
    is what surfaced this: BOTH arms hand-rolled `requests`, and the header
    gate made hand-rolling *more* attractive, since sending a header is one
    line there and a config change in dlt.

    No exemption for a connectivity probe, because `api-source.md`'s Self-check
    section states the rule this enforces: the probe is a standalone script
    beside the closure, never inside `transform/`. A probe under `transform/`
    would re-run on every materialization the supervisor performs.

    This does NOT contradict `reference/self-check.md`'s waiver of the transport
    family for api-source closures. That waiver covers IMPORTS -- dlt's REST
    source is built on `requests`/`httpx`/`urllib3`, so a reach scan fires on
    every correct API closure. This gate keys on CALLS the closure's own source
    makes: a correct dlt closure never calls `requests.get` itself, because dlt
    does that inside dlt. Imports are waived; hand-written calls are not.
    """
    if not (root / "transform").is_dir():
        return False, "no transform/ directory"
    sources = transform_sources(root)
    if not sources:
        return False, "no transform/*.py sources"

    uses_connector = False
    hand_rolled: list[str] = []
    for path in sources:
        try:
            tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
        except SyntaxError as exc:
            return False, f"{path.name} does not parse: {exc}"
        uses_connector = uses_connector or _uses_dlt_rest(tree)
        hand_rolled += [f"{path.name}:{c}" for c in _http_client_calls(tree)]

    if hand_rolled and uses_connector:
        return False, (
            f"HYBRID -- imports dlt's REST connector but also fetches HTTP by hand "
            f"({', '.join(hand_rolled)}). Ingestion must go THROUGH the connector, "
            f"not beside it; a RESTAPIConfig that exists but does not carry the "
            f"requests is not the required architecture"
        )
    if hand_rolled:
        return False, (
            f"ingestion hand-rolls HTTP ({', '.join(hand_rolled)}) instead of "
            f"dlt's REST connector -- no dlt.sources.rest_api import / "
            f"rest_api_resources(...) call found"
        )
    if not uses_connector:
        return False, "no dlt.sources.rest_api import / rest_api_resources(...) call found"
    return True, ""


def headers_built_from_secrets(
    root: Path, header_value: str
) -> tuple[bool, str]:
    """The transform assembles dlt's `client["headers"]` from the flat
    `header_*` secrets rather than hardcoding the required header.

    Two independent failure modes, distinguished in the detail because the fixes
    differ: never configuring headers at all (the closure 403s), versus
    configuring them from a literal (the closure works today and breaks the
    moment the profile changes, exactly like a hardcoded base_url).

    `header_value` is the value the upstream requires — the caller's, because
    each scenario's fixture gates on its own. A closure that carries it as a
    literal has hardcoded it, wherever the profile also happens to declare it.

    This is the fact a supervisor E2E cannot infer from the wire. A closure with
    the User-Agent frozen into `transform/main.py` sends exactly the right
    header, so the fixture sees a perfect request and every observation-based
    check passes — while the closure is one profile change away from 403ing
    everywhere. Only reading the source can see it, which is why this moved here
    rather than staying in the one checker that had it.

    The hardcode test reads STRING LITERALS via the AST, docstrings excluded --
    not the file text. A correct closure that documents why the header exists
    ("Beacon rejects any client not sending User-Agent: nexty-test-client/1.0")
    is explaining the requirement, not hardcoding it, and a substring scan
    reports that comment as the very defect the comment is warning about.

    Scans every `transform/*.py` for the same reason the connector gate does:
    a closure that factors `_headers_from` into `transform/http.py` and calls it
    from `main.py` is correct, and a main-only scan calls it a closure that
    never reads a header.
    """
    sources = transform_sources(root)
    if not sources:
        return False, "no transform/*.py sources"

    literals: list[str] = []
    text_of: list[str] = []
    for path in sources:
        src = path.read_text(encoding="utf-8", errors="replace")
        text_of.append(src)
        try:
            literals += string_literals(ast.parse(src))
        except SyntaxError as exc:
            return False, f"{path.name} does not parse: {exc}"

    if any(header_value in lit for lit in literals):
        return False, (f"transform hardcodes {header_value!r} instead of reading "
                       f"it from the flat secrets map (secrets['header_user_agent'])")

    joined = "\n".join(text_of)
    reads_header_secrets = bool(
        re.search(r"""startswith\(\s*['"]header_""", joined)
        or re.search(r"""secrets\s*(?:\.get\s*\(\s*|\[\s*)['"]header_\w+['"]""", joined)
        or any(lit.startswith("header_") for lit in literals)
    )
    if not reads_header_secrets:
        return False, ("transform never reads a header_* key from secrets — the API "
                       "requires a header and rejects the request without it")
    sets_headers = bool(re.search(r"""['"]headers['"]\s*\]?\s*[=:]""", joined))
    if not sets_headers:
        return False, ("transform reads header_* secrets but never assigns them to the "
                       "RESTAPIConfig client's `headers` key")
    return True, ""


def no_hardcoded_url_or_path(
    root: Path, hosts: tuple[str, ...], paths: tuple[str, ...]
) -> tuple[bool, str]:
    """Host and endpoint path come from `secrets`, not from a literal.

    Reads STRING LITERALS via the AST, docstrings excluded -- not the file
    text. A correct closure that documents which endpoints it serves ("reads
    /v2/country via secrets['endpoint_economies']") is explaining the
    topology, not freezing it, and a substring scan over the raw source reports
    that comment as the very defect the comment describes. Same reasoning
    `headers_built_from_secrets` gives for the User-Agent, and the same
    reasoning `reference/self-check.md` gives for reading `spec.py`'s literals
    via the AST rather than its text.

    `hosts` and `paths` are per-scenario: the fixture's host (or `127.0.0.1`
    for a local stub) and the endpoint path prefixes the brief names. Pass
    prefixes rather than whole paths -- `/v2/country` catches
    `/v2/country/all/indicator/...` too, and an endpoint frozen at any depth is
    the same defect.
    """
    sources = transform_sources(root)
    if not sources:
        return False, "no transform/*.py sources"
    literals: list[str] = []
    for path in sources:
        try:
            literals += string_literals(ast.parse(
                path.read_text(encoding="utf-8", errors="replace")))
        except SyntaxError as exc:
            return False, f"{path.name} does not parse: {exc}"

    for host in hosts:
        if any(host in lit for lit in literals):
            return False, (f"transform hardcodes the host {host!r} instead of "
                           f"reading secrets['base_url']")
    for path_prefix in paths:
        if any(path_prefix in lit for lit in literals):
            return False, (f"transform hardcodes the endpoint path {path_prefix!r} "
                           f"instead of reading secrets['endpoint_<model>']")
    return True, ""

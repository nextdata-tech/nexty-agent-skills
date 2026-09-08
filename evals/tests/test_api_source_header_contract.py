"""The custom-request-header path for api-source closures (NEX-873).

An upstream REST API can reject a perfectly credentialed request over a header
that has nothing to do with auth. dlt sends ``User-Agent: dlt/1.28.2`` by
default; an API that filters unknown clients answers 403 with a body about
permissions. The observed failure mode was an author reading that as a
credential problem, then abandoning the dlt REST connector for a hand-rolled
``urllib`` loop with a custom User-Agent — off the supported architecture, and
invisible to every check that only asks whether rows landed.

Three layers, because each can rot independently:

1. **The doc contract** — ``api-source.md`` must teach the ``header_`` prefix,
   the ``client["headers"]`` assembly, and the ``public: true`` classification.
   Pure text assertions, no dependencies.
2. **The doc's own code** — ``_headers_from`` is EXTRACTED from the reference
   and executed here, so the snippet an author copies is the snippet under
   test. A copy in this file would drift from the doc silently, which is the
   failure this layer exists to prevent.
3. **The wire** — the pinned ``dlt==1.28.2`` really does forward
   ``client["headers"]``, proved against the scenario's own header-gated stub.
   This is the layer that catches a dlt bump renaming or dropping the field:
   the recipe would still read correctly and every closure would 403.

Layer 3 runs dlt in a subprocess via ``uv run --with`` (the same idiom
``check_authenticated_api_source.py`` uses to materialize a closure) so the
pytest environment stays lean. It does NOT skip when dlt is absent — a silent
skip here would mean the connector contract goes unverified in exactly the CI
run that was supposed to verify it.
"""

from __future__ import annotations

import ast
import json
import re
import subprocess
import textwrap
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
API_SOURCE = (REPO_ROOT / "src" / "nxd-generate-data-product" / "reference" /
              "api-source.md")
FIXTURES = (REPO_ROOT / "evals" / "public" / "authenticated-api-source-build" /
            "fixtures")
STUB = FIXTURES / "stub_beacon_api.py"

DLT_PIN = "dlt[duckdb]==1.28.2"
SUBPROCESS_TIMEOUT_S = 600


# ---------------------------------------------------------------------------
# Layer 1: the doc contract
# ---------------------------------------------------------------------------


def _doc() -> str:
    return API_SOURCE.read_text(encoding="utf-8")


def test_recipe_documents_the_header_prefix():
    t = _doc()
    assert "## Custom request headers" in t, (
        "api-source.md must carry a Custom request headers section"
    )
    assert "header_user_agent" in t and "`header_` prefix" in t, (
        "the recipe must teach the header_<name> attribute convention"
    )
    # The Contents block is the loader's index into a 500-line reference.
    head = "\n".join(t.splitlines()[:25])
    assert "Custom request headers" in head, (
        "Custom request headers must appear in the ## Contents list"
    )


def test_recipe_names_the_dlt_default_user_agent():
    # The concrete fact that turns an opaque 403 into a five-second diagnosis.
    # Without it the section reads as "you may set headers" rather than "this
    # is why your credentialed request is being refused".
    t = _doc()
    assert "dlt/1.28.2" in t, (
        "the recipe must name dlt's default User-Agent — it is the reason the "
        "403 appears while the same credentials succeed under curl"
    )
    assert "403" in t


def test_recipe_forbids_secret_valued_headers_under_the_prefix():
    # header_* is public: true and survives export verbatim. A token filed
    # there is an exported credential, so the recipe must route secret-valued
    # headers to auth_type: api_key instead.
    t = _doc().lower()
    assert "header_authorization" in t, (
        "the recipe must name the header_authorization mis-filing explicitly"
    )
    assert re.search(r"api_key", t), (
        "the recipe must route secret-valued headers to auth_type: api_key"
    )


def test_recipe_classifies_headers_as_public():
    t = _doc()
    assert re.search(r"`header_\*`[^\n]{0,80}`public: true`", t) or re.search(
        r"every `header_\*` — is `public: true`", t
    ), "api-source.md must classify header_* attributes as public: true"


def test_recipe_keeps_header_values_redacted_by_default():
    # _PUBLIC_SUFFIXES is the probe's exemption list. header_* is deliberately
    # NOT on it: a mis-filed credential must still be redacted from a traceback.
    t = _doc()
    assert "deliberately NOT exempt" in t, (
        "the recipe must state that header_* stays subject to probe redaction"
    )
    suffixes = re.search(r"_PUBLIC_SUFFIXES = \((.*?)\)", t, re.DOTALL)
    assert suffixes, "api-source.md must define _PUBLIC_SUFFIXES"
    assert "header" not in suffixes.group(1), (
        "header_* must not be exempted from probe redaction — the exemption "
        "list is what stands between a mis-filed credential and the transcript"
    )


# ---------------------------------------------------------------------------
# Layer 2: the doc's own code
# ---------------------------------------------------------------------------


def _extract_headers_from() -> str:
    """Pull only `_headers_from` from the executable refresh block."""
    blocks = re.findall(r"```python\n(.*?)```", _doc(), re.DOTALL)
    for block in blocks:
        if "def _headers_from" in block:
            source = textwrap.dedent(block)
            tree = ast.parse(source)
            lines = source.splitlines(keepends=True)
            for node in tree.body:
                if (
                    isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                    and node.name == "_headers_from"
                ):
                    return "".join(lines[node.lineno - 1 : node.end_lineno])
    raise AssertionError(
        "api-source.md must define _headers_from in a ```python block — the "
        "transform assembly the recipe teaches is what these tests execute"
    )


def _load_headers_from():
    namespace: dict = {}
    exec(compile(_extract_headers_from(), "<api-source.md>", "exec"), namespace)
    return namespace["_headers_from"]


def test_doc_snippet_maps_prefix_to_header_names():
    headers_from = _load_headers_from()
    assert headers_from({"header_user_agent": "acme/1.0"}) == {"User-Agent": "acme/1.0"}
    assert headers_from({"header_x_trace_id": "abc"}) == {"X-Trace-Id": "abc"}
    assert headers_from({"header_accept": "application/json"}) == {
        "Accept": "application/json"
    }


def test_doc_snippet_ignores_non_header_secrets():
    # The flat secrets map carries base_url, auth_*, and any co-located
    # service's fields. Only header_* may reach the wire as a header — an
    # over-broad scan would put the bearer token in a header named Auth-Token.
    headers_from = _load_headers_from()
    assert headers_from({
        "base_url": "https://example.invalid",
        "auth_type": "bearer",
        "auth_token": "secret-value",
        "orders_host": "db.invalid",
    }) == {}


def test_doc_snippet_skips_empty_values():
    # An attribute present but blank must not send an empty header, which some
    # servers treat differently from an absent one.
    headers_from = _load_headers_from()
    assert headers_from({"header_user_agent": "", "header_accept": None}) == {}


def test_doc_snippet_stringifies_values():
    # Supervisor-delivered values are always strings, but a hand-built dict in
    # a self-check probe may not be; dlt requires Dict[str, str].
    headers_from = _load_headers_from()
    assert headers_from({"header_x_retry": 3}) == {"X-Retry": "3"}


# ---------------------------------------------------------------------------
# Layer 3: the wire
# ---------------------------------------------------------------------------

_WIRE_PROOF = '''
import importlib.util, json, sys

spec = importlib.util.spec_from_file_location("_stub", sys.argv[1])
stub = importlib.util.module_from_spec(spec)
spec.loader.exec_module(stub)

from dlt.sources.rest_api import RESTAPIConfig, rest_api_resources
from dlt.sources.rest_api.typing import ClientConfig

result = {"has_headers_field": "headers" in ClientConfig.__annotations__}

server, port, thread = stub.start_server()
base_url = f"http://127.0.0.1:{port}"


def drain(headers):
    client = {"base_url": base_url,
              "auth": {"type": "bearer", "token": stub.VALID_TOKEN},
              "paginator": {"type": "page_number", "base_page": 1,
                            "page_param": "page", "total_path": "pages"}}
    if headers is not None:
        client["headers"] = headers
    cfg: RESTAPIConfig = {"client": client,
                          "resources": [{"name": "monitors",
                                         "endpoint": {"path": "/v1/monitors",
                                                      "data_selector": "data"}}]}
    rows = []
    for resource in rest_api_resources(cfg):
        rows.extend(list(resource))
    return rows


try:
    # Control: no client headers. dlt's own default User-Agent is exactly the
    # unrecognized client the stub refuses, so this must fail.
    stub.reset_observations()
    try:
        drain(None)
        result["control_landed_rows"] = True
    except Exception as exc:
        result["control_landed_rows"] = False
        result["control_error"] = type(exc).__name__
    result["control_user_agents"] = sorted({ua for _, ua, _ in stub.observations()})

    # Treatment: the header the recipe configures.
    stub.reset_observations()
    rows = drain({"User-Agent": stub.REQUIRED_USER_AGENT})
    result["treatment_rows"] = len(rows)
    observed = stub.observations()
    result["treatment_user_agents"] = sorted({ua for _, ua, _ in observed})
    result["treatment_all_authorized"] = all(a for _, _, a in observed)
finally:
    stub.stop_server(server, thread)

print("__RESULT__" + json.dumps(result))
'''


@pytest.fixture(scope="module")
def wire_proof(tmp_path_factory) -> dict:
    """Run the header proof against a real dlt==1.28.2 in a throwaway env.

    The script goes to a tmp dir, never beside this file: an interrupted run
    would otherwise leave a stray module in `evals/tests/` that pytest's next
    collection walks over.
    """
    script = tmp_path_factory.mktemp("header-wire-proof") / "proof.py"
    script.write_text(textwrap.dedent(_WIRE_PROOF), encoding="utf-8")
    try:
        proc = subprocess.run(
            ["uv", "run", "--no-project", "--with", DLT_PIN,
             "python", str(script), str(STUB)],
            capture_output=True, text=True, timeout=SUBPROCESS_TIMEOUT_S,
        )
    except FileNotFoundError:  # pragma: no cover - environment defect
        pytest.fail("uv is required to verify the dlt header contract and was not found")
    except subprocess.TimeoutExpired:  # pragma: no cover
        pytest.fail(f"dlt header proof timed out after {SUBPROCESS_TIMEOUT_S}s")

    if proc.returncode != 0:
        pytest.fail(
            "dlt header proof failed to run against "
            f"{DLT_PIN}:\n{(proc.stderr or proc.stdout)[-3000:]}"
        )
    marker = [ln for ln in proc.stdout.splitlines() if ln.startswith("__RESULT__")]
    assert marker, f"proof produced no result line:\n{proc.stdout[-3000:]}"
    return json.loads(marker[-1][len("__RESULT__"):])


def test_pinned_dlt_exposes_a_client_headers_field(wire_proof):
    # If a dlt bump renames or drops this, the recipe still reads correctly and
    # every generated api-source closure starts 403ing against a header-gated
    # upstream. Fail here, at the pin, rather than there.
    assert wire_proof["has_headers_field"], (
        f"{DLT_PIN} ClientConfig no longer declares a `headers` field — the "
        "api-source recipe's Custom request headers section is now wrong"
    )


def test_unconfigured_client_is_refused_by_the_header_gate(wire_proof):
    # The control arm. Without it, a stub that stopped enforcing the header
    # would let the treatment arm pass for the wrong reason.
    assert wire_proof["control_landed_rows"] is False, (
        "the stub accepted a request with dlt's default User-Agent — the "
        "header gate is not enforcing, so the treatment arm proves nothing"
    )
    assert wire_proof["control_user_agents"] == ["dlt/1.28.2"], (
        "expected dlt's own default User-Agent on the control request, got "
        f"{wire_proof['control_user_agents']}"
    )


def test_configured_header_reaches_the_outbound_request(wire_proof):
    assert wire_proof["treatment_user_agents"] == ["nexty-test-client/1.0"], (
        "the configured client header did not reach the wire; observed "
        f"{wire_proof['treatment_user_agents']}"
    )
    assert wire_proof["treatment_rows"] == 12, (
        f"expected all 12 monitors to land, got {wire_proof['treatment_rows']}"
    )


def test_client_headers_do_not_displace_auth(wire_proof):
    # client["headers"] and client["auth"] both write request headers. If the
    # mapping replaced rather than merged, configuring a User-Agent would strip
    # Authorization and the failure would read as a bad credential.
    assert wire_proof["treatment_all_authorized"], (
        "configuring client headers dropped the Authorization header"
    )

"""A failing api-source request must not put the credential in the transcript.

NEX-873's second acceptance criterion: secret-valued headers keep using the
supervisor's secret-injection mechanism and are redacted from diagnostics,
exports, and error reporting. Two distinct paths carry that risk, and they fail
for different reasons:

* **The connector.** dlt sends the credential as an `Authorization` header
  built by the `auth` dispatch. A 4xx raises through dlt's own exception chain,
  which the supervisor surfaces as a build diagnostic. Nothing in the closure
  redacts that text — the guarantee is that the header value is never in it.
* **The probe.** `api-source.md`'s connectivity smoke test is a hand-written
  standalone script, and `requests` puts the FULL URL in an `HTTPError`
  message. An API keyed by query string (`?api_key=…`) leaks the live
  credential into chat on the first failed probe — the one place the user
  cannot remediate. The guarantee here is `_redact`, and the recipe's own code
  is what these tests execute.

Three layers, because each rots independently:

1. **The doc contract** — the exemption list api-source.md shares with
   database-source.md really is the same list, and `from None` is stated as
   mandatory in both.
2. **The doc's own code** — `_redact` is EXTRACTED from the reference and run
   here against a synthetic credential. A copy in this file would drift from
   the doc silently, which is the failure this layer exists to prevent.
3. **The wire** — a real 4xx from the pinned `dlt==1.28.2` and from a real
   `requests` probe, against the scenario's own stub. The probe arm asserts the
   leak is REAL before asserting the redactor removes it: without that control,
   a redactor that matched nothing would pass every test in this file.

Layer 3 runs in a subprocess via `uv run --with` (the idiom
`test_api_source_header_contract.py` and `check_authenticated_api_source.py`
both use) so the pytest environment stays lean. It does NOT skip when dlt is
absent — a silent skip here means the credential contract went unverified in
exactly the CI run that was supposed to verify it.
"""

from __future__ import annotations

import ast
import json
import re
import subprocess
import textwrap
import traceback
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
REFERENCE = REPO_ROOT / "src" / "nxd-generate-data-product" / "reference"
API_SOURCE = REFERENCE / "api-source.md"
DATABASE_SOURCE = REFERENCE / "database-source.md"
STUB = (REPO_ROOT / "evals" / "public" / "authenticated-api-source-build" /
        "fixtures" / "stub_beacon_api.py")

DLT_PIN = "dlt[duckdb]==1.28.2"
SUBPROCESS_TIMEOUT_S = 600

# Recognizable and obviously synthetic: if either string ever appears in a
# failure message here, the assertion that printed it is the one that matters.
SECRET_TOKEN = "bcn_live_SYNTHETIC_TOKEN_0123456789abcdef"  # noqa: S105 - fixture
SECRET_QUERY_KEY = "bcn_live_SYNTHETIC_QUERY_fedcba9876543210"  # noqa: S105 - fixture


def _redact_block(doc: Path) -> str:
    """The ```python block defining `_redact`, verbatim from a reference."""
    blocks = re.findall(r"```python\n(.*?)```", doc.read_text(encoding="utf-8"),
                        re.DOTALL)
    for block in blocks:
        if "def _redact" in block:
            return block
    raise AssertionError(
        f"{doc.name} must define _redact in a ```python block — the redaction "
        f"an author copies is what these tests execute")


def _load_redact(doc: Path = API_SOURCE):
    namespace: dict = {}
    # The block ends with the taught `try: ... except: ... from None`. The try
    # body is an Ellipsis placeholder, so it succeeds and the handler (which
    # references an undefined `secrets`) is never evaluated.
    exec(compile(_redact_block(doc), f"<{doc.name}>", "exec"), namespace)
    return namespace["_redact"]


def _suffixes(doc: Path) -> tuple[str, ...]:
    match = re.search(r"_PUBLIC_SUFFIXES = (\(.*?\))", doc.read_text(encoding="utf-8"),
                      re.DOTALL)
    assert match, f"{doc.name} must define _PUBLIC_SUFFIXES"
    return ast.literal_eval(match.group(1))


# ---------------------------------------------------------------------------
# Layer 1: the doc contract
# ---------------------------------------------------------------------------


def test_the_two_references_share_one_exemption_list():
    """api-source.md claims "the same exemption list as database-source.md".

    A closure naming both an api-source and a db-source hands one probe the
    whole flat map, so the two lists are not merely similar by coincidence —
    they govern the same values. Drift makes one doc's claim false, and the
    reader who trusts it exempts a key the other redacts.
    """
    assert _suffixes(API_SOURCE) == _suffixes(DATABASE_SOURCE), (
        "the exemption lists have drifted; api-source.md states they are one "
        "pattern with two call sites"
    )


def test_both_references_mandate_from_none():
    for doc in (API_SOURCE, DATABASE_SOURCE):
        text = doc.read_text(encoding="utf-8")
        assert "from None" in text and "`from None` is mandatory" in text, (
            f"{doc.name} must state that `from None` is mandatory — without it "
            f"Python chains the original exception and re-prints it in full, "
            f"defeating the redaction"
        )


def test_endpoint_keys_stay_readable():
    """Redacting the endpoint path out of a failing URL hides the diagnosis.

    `endpoint_<model>` cannot be reached by the suffix rule (the model name is
    the tail and is author-chosen), so the recipe matches the segment instead.
    Without it a 404 on the wrong endpoint — the likeliest thing to go wrong at
    this step — prints as `https://api.example.com<redacted>`.
    """
    text = API_SOURCE.read_text(encoding="utf-8")
    match = re.search(r"_PUBLIC_SEGMENTS = (\(.*?\))", text, re.DOTALL)
    assert match, "api-source.md must define _PUBLIC_SEGMENTS"
    assert "endpoint_" in ast.literal_eval(match.group(1))


# ---------------------------------------------------------------------------
# Layer 2: the doc's own code
# ---------------------------------------------------------------------------


def _secrets(**over) -> dict:
    """A flat secrets map shaped like a real closure's, plus overrides."""
    base = {
        "base_url": "https://api.example.invalid",
        "auth_type": "bearer",
        "auth_token": SECRET_TOKEN,
        "endpoint_monitors": "/v1/monitors",
        "header_user_agent": "nexty-test-client/1.0",
    }
    base.update(over)
    return base


def test_credential_is_substituted_not_pattern_matched():
    redact = _load_redact()
    exc = RuntimeError(f"401 for url: https://api.example.invalid/v1/monitors "
                       f"(sent Authorization: Bearer {SECRET_TOKEN})")
    out = redact(exc, _secrets())
    assert SECRET_TOKEN not in out
    assert "<redacted>" in out


def test_public_topology_survives_so_the_error_is_actionable():
    """"could not connect to <redacted>" tells the user nothing they can act on."""
    redact = _load_redact()
    exc = RuntimeError("404 for url: https://api.example.invalid/v1/monitors")
    out = redact(exc, _secrets())
    assert "https://api.example.invalid" in out
    assert "/v1/monitors" in out, (
        "the endpoint path must stay readable — a 404 that names neither the "
        "endpoint nor the model is undiagnosable"
    )


def test_a_query_string_credential_goes():
    redact = _load_redact()
    exc = RuntimeError(
        f"401 Client Error: Unauthorized for url: "
        f"https://api.example.invalid/v1/monitors?api_key={SECRET_QUERY_KEY}")
    out = redact(exc, _secrets(auth_api_key=SECRET_QUERY_KEY))
    assert SECRET_QUERY_KEY not in out
    assert "api_key=<redacted>" in out


def test_a_mis_filed_credential_in_a_header_is_still_redacted():
    """`header_*` is non-secret by convention, and NOT exempt from redaction.

    `header_authorization` holding a token is exactly the mis-filing the
    convention warns about. A redacted User-Agent in an error message costs
    nothing; the reverse mistake cannot be taken back.
    """
    redact = _load_redact()
    exc = RuntimeError(f"403 rejected (Authorization: {SECRET_TOKEN})")
    out = redact(exc, _secrets(auth_token="", header_authorization=SECRET_TOKEN))
    assert SECRET_TOKEN not in out


def test_a_co_located_database_password_goes_too():
    """`secrets` is the WHOLE flat map, not just this service's attributes."""
    redact = _load_redact()
    exc = RuntimeError("connection refused for db.internal:5432 "
                       "(password=hunter2-synthetic)")
    out = redact(exc, _secrets(orders_password="hunter2-synthetic",
                               orders_host="db.internal", orders_port="5432"))
    assert "hunter2-synthetic" not in out
    assert "db.internal" in out and "5432" in out, (
        "host/port are the diagnostic and are exempt by suffix"
    )


def test_an_empty_value_does_not_blank_the_message():
    """`str.replace("", x)` interleaves x between every character."""
    redact = _load_redact()
    exc = RuntimeError("404 for url: https://api.example.invalid/v1/monitors")
    out = redact(exc, _secrets(auth_token="", auth_password=None))
    assert out == "404 for url: https://api.example.invalid/v1/monitors"


def test_from_none_stops_the_original_traceback_reprinting():
    """The redacted message is worthless if Python re-prints the raw one below it.

    Both arms here, because the control is what makes the assertion mean
    something: chaining leaks, `from None` does not.
    """
    redact = _load_redact()
    secrets = _secrets()

    def _formatted(suppress: bool) -> str:
        try:
            try:
                raise RuntimeError(f"401 for url: https://x.invalid?k={SECRET_TOKEN}")
            except Exception as exc:
                message = f"connectivity check failed: {redact(exc, secrets)}"
                if suppress:
                    raise SystemExit(message) from None
                raise SystemExit(message)  # noqa: B904 - the control arm
        except SystemExit as exc:
            return "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))

    assert SECRET_TOKEN in _formatted(suppress=False), (
        "control arm: without `from None` the chained original must still leak, "
        "or this test proves nothing about the suppression"
    )
    assert SECRET_TOKEN not in _formatted(suppress=True)


# ---------------------------------------------------------------------------
# Layer 3: the wire
# ---------------------------------------------------------------------------

_WIRE_PROOF = '''
import importlib.util, json, sys, traceback

spec = importlib.util.spec_from_file_location("_stub", sys.argv[1])
stub = importlib.util.module_from_spec(spec)
spec.loader.exec_module(stub)

namespace = {}
exec(compile(open(sys.argv[2]).read(), "<api-source.md>", "exec"), namespace)
_redact = namespace["_redact"]

SECRET_TOKEN = sys.argv[3]
SECRET_QUERY_KEY = sys.argv[4]

result = {}
server, port, thread = stub.start_server()
base_url = f"http://127.0.0.1:{port}"
secrets = {"base_url": base_url, "auth_type": "bearer", "auth_token": SECRET_TOKEN,
           "auth_api_key": SECRET_QUERY_KEY, "endpoint_monitors": "/v1/monitors",
           "header_user_agent": stub.REQUIRED_USER_AGENT}

try:
    # --- arm A: the connector. A wrong bearer token 401s; the token travels as
    # an Authorization header, and dlt's exception chain is what the supervisor
    # surfaces as a build diagnostic.
    from dlt.sources.rest_api import rest_api_resources

    cfg = {"client": {"base_url": base_url,
                      "headers": {"User-Agent": stub.REQUIRED_USER_AGENT},
                      "auth": {"type": "bearer", "token": SECRET_TOKEN}},
           "resources": [{"name": "monitors",
                          "endpoint": {"path": "/v1/monitors",
                                       "data_selector": "data"}}]}
    try:
        for resource in rest_api_resources(cfg):
            list(resource)
        result["connector_raised"] = False
    except Exception as exc:
        result["connector_raised"] = True
        result["connector_status_named"] = "401" in str(exc)
        result["connector_leaks_token"] = (
            SECRET_TOKEN in str(exc) or SECRET_TOKEN in traceback.format_exc())

    # --- arm B: the probe. A hand-written bounded GET with the credential in
    # the query string -- the shape api-source.md's Self-check section governs.
    import requests

    try:
        response = requests.get(f"{base_url}/v1/monitors",
                                params={"api_key": SECRET_QUERY_KEY},
                                headers={"User-Agent": stub.REQUIRED_USER_AGENT},
                                timeout=10)
        response.raise_for_status()
        result["probe_raised"] = False
    except Exception as exc:
        result["probe_raised"] = True
        raw = str(exc)
        redacted = _redact(exc, secrets)
        result["probe_raw_leaks"] = SECRET_QUERY_KEY in raw
        result["probe_redacted_leaks"] = SECRET_QUERY_KEY in redacted
        result["probe_redacted_keeps_base_url"] = base_url in redacted
        result["probe_redacted_keeps_endpoint"] = "/v1/monitors" in redacted
finally:
    stub.stop_server(server, thread)

print("__RESULT__" + json.dumps(result))
'''


@pytest.fixture(scope="module")
def wire_proof(tmp_path_factory) -> dict:
    scratch = tmp_path_factory.mktemp("redaction-wire-proof")
    script = scratch / "proof.py"
    script.write_text(textwrap.dedent(_WIRE_PROOF), encoding="utf-8")
    # The recipe's own redactor, extracted here and executed there.
    recipe = scratch / "recipe.py"
    recipe.write_text(_redact_block(API_SOURCE), encoding="utf-8")
    try:
        proc = subprocess.run(
            ["uv", "run", "--no-project", "--with", DLT_PIN, "--with", "requests",
             "python", str(script), str(STUB), str(recipe),
             SECRET_TOKEN, SECRET_QUERY_KEY],
            capture_output=True, text=True, timeout=SUBPROCESS_TIMEOUT_S,
        )
    except FileNotFoundError:  # pragma: no cover - environment defect
        pytest.fail("uv is required to verify the redaction contract and was not found")
    except subprocess.TimeoutExpired:  # pragma: no cover
        pytest.fail(f"redaction proof timed out after {SUBPROCESS_TIMEOUT_S}s")

    if proc.returncode != 0:
        pytest.fail("redaction proof failed to run against "
                    f"{DLT_PIN}:\n{(proc.stderr or proc.stdout)[-3000:]}")
    marker = [ln for ln in proc.stdout.splitlines() if ln.startswith("__RESULT__")]
    assert marker, f"proof produced no result line:\n{proc.stdout[-3000:]}"
    return json.loads(marker[-1][len("__RESULT__"):])


def test_connector_error_names_the_status_without_the_credential(wire_proof):
    """The shipped ingestion path's 4xx diagnostic must carry no token.

    dlt puts the failing URL in its exception chain and the credential in an
    Authorization header. If a bump ever started echoing request headers into
    that message, every generated api-source closure would leak its bearer
    token into the supervisor's diagnostics on the first 401 — with no closure
    code in a position to redact it.
    """
    assert wire_proof["connector_raised"], (
        "the stub accepted a wrong bearer token — the arm proves nothing")
    assert wire_proof["connector_status_named"], (
        "the connector's error must still name the 401, or a real failure is "
        "undiagnosable")
    assert not wire_proof["connector_leaks_token"]


def test_probe_error_leaks_before_redaction(wire_proof):
    """The control. A redactor that matched nothing would pass everything else."""
    assert wire_proof["probe_raised"]
    assert wire_proof["probe_raw_leaks"], (
        "requests no longer puts the query string in HTTPError — the risk the "
        "recipe's _redact exists for may have changed shape")


def test_probe_error_is_redacted_and_still_diagnosable(wire_proof):
    assert not wire_proof["probe_redacted_leaks"]
    assert wire_proof["probe_redacted_keeps_base_url"]
    assert wire_proof["probe_redacted_keeps_endpoint"]

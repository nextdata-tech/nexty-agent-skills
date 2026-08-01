"""Phase E — the reach gate — must decide BEFORE the transform executes.

Two things are pinned here, and the first is the one that rots silently.

**Ordering.** Phase B imports ``transform.main`` and calls ``ingest(...)``. A
reach scan placed anywhere after that reports "denied" once the transform has
already opened the socket, already called the model, already spent the money —
and it still prints a red banner, so the failure looks like it worked. The
ordering is therefore not a stylistic choice about where the block reads best;
it is the entire mechanism. ``test_phase_e_decides_before_phase_b_imports``
asserts the byte offsets, so moving the block below ``sys.path.insert`` fails
here rather than degrading into a post-hoc report nobody notices.

**The rule.** The invariant "the transform never calls a model" was shipped as
prose on the belief that the desktop venv was closed. It is not: ``requests``,
``httpx``, ``httpcore`` and ``urllib3`` all arrive transitively via ``dlt`` and
``mcp``, and ``urllib``/``socket`` are stdlib. These tests run the extracted
block against synthetic closures so that a rule which stops firing — the usual
end state of a gate with no test — fails visibly.

The scope boundary is asserted too, in ``test_wrapped_socket_is_invisible`` and
``test_url_handed_to_a_reader_is_invisible``: those closures PASS, deliberately.
Pinning what the gate cannot see keeps a later reader from mistaking a green
Phase E for proof that the transform is offline.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

EVALS_DIR = Path(__file__).resolve().parents[1]
SELF_CHECK_MD = (
    EVALS_DIR.parent / "src" / "nxd-generate-dp" / "reference" / "self-check.md"
)

CSV = '_csv = "/infra-profile/desktop-local#/services/csv-source"\n'
FILE = '_f = "/infra-profile/desktop-local#/services/file-source"\n'
API = '_api = "/infra-profile/desktop-local#/services/api-source"\n'
API_LABELLED = '_a = "/infra-profile/desktop-local#/services/api-source-github"\n'
DB = '_db = "/infra-profile/desktop-local#/services/db-source-orders"\n'
NO_SOURCE = '_c = "/infra-profile/desktop-local#/services/python-compute"\n'

CLEAN_CSV_TRANSFORM = (
    "import dlt\n"
    "from dlt.sources.filesystem import filesystem, read_csv\n"
    "from nxd import data_product\n"
    "import os\n"
    "from pathlib import Path\n"
)


def _script_body() -> str:
    """The single ``# self_check.py`` fence, same source the agent runs."""
    blocks = re.findall(r"```python\n(.*?)```", SELF_CHECK_MD.read_text(), re.S)
    bodies = [b for b in blocks if b.lstrip().startswith("# self_check.py")]
    assert len(bodies) == 1, f"expected one self_check.py fence, found {len(bodies)}"
    return bodies[0]


def _phase_e_source() -> str:
    """Phase E's block, from ``eerrors = []`` to the Phase B banner."""
    body = _script_body()
    block = body[body.index("eerrors = []"):body.index("Phase B ---")]
    return block[:block.rindex("\n#")]


def _run_phase_e(
    tmp_path: Path, spec_src: str, transform_src: str, *, expect_exit: int
) -> str:
    """Execute Phase E standalone against a synthetic closure.

    Phase E reads only ``spec_src`` and ``transform_src``, both already in scope
    at that point in the real script, so the harness supplies them directly
    rather than materialising a whole closure.

    ``expect_exit`` is mandatory, and that is the point. The banner text and the
    exit code are independent: printing "PHASE E FAILED" is what a reader sees,
    but ``sys.exit(1)`` is what actually stops the run before Phase B imports the
    transform. Asserting only the text would leave the gate green-lighting a
    denied closure the moment the exit was dropped — the whole mechanism gone,
    every text assertion still passing.
    """
    harness = (
        "import ast, json, re, sys\n"
        "from pathlib import Path\n"
        # Phase E reports through the shared diagnostic surface rather than bare
        # print/sys.exit. These stubs stand in for the part of the script above
        # Phase E, and they are deliberately faithful on the two properties this
        # file asserts: `say` writes to stdout, so the banner text is still
        # checked, and `finish` really exits, so the ordering guarantee remains a
        # real process exit rather than a returned value nobody reads.
        #
        # Emitted diagnostics are dumped as JSON on the way out so a test can
        # assert the CODE and not only the prose. The code is what the build
        # record and its consumers key on; a rule that fires with the wrong code
        # is as broken as one that does not fire, and prose assertions cannot
        # tell the difference.
        "DIAGS = []\n"
        "def say(*a, **k): print(*a, **k)\n"
        "def cpath(at): return f'closure:{at}' if at else ''\n"
        "def diag(stage, code, message, *, path='', evidence=None, fix=None):\n"
        "    DIAGS.append({'stage': stage, 'code': code, 'path': path})\n"
        "def close_stage(stage, state, **detail): pass\n"
        "def _dump(): print('DIAGS_JSON=' + json.dumps(DIAGS))\n"
        "def finish(code):\n"
        "    _dump()\n"
        "    sys.exit(code)\n"
        f"spec_src = {spec_src!r}\n"
        f"transform_src = {transform_src!r}\n"
    ) + _phase_e_source() + "\n_dump()\n"
    script = tmp_path / "_phase_e.py"
    script.write_text(harness, encoding="utf-8")
    proc = subprocess.run(
        [sys.executable, str(script)], cwd=tmp_path, capture_output=True, text=True
    )
    out = proc.stdout + proc.stderr
    assert "Traceback" not in out, out
    assert proc.returncode == expect_exit, (
        f"expected exit {expect_exit}, got {proc.returncode}. A deny must exit 1 "
        f"(the run stops before Phase B imports the transform); an allow must "
        f"exit 0.\n{out}"
    )
    return out


def _findings(out: str) -> list[str]:
    return [ln.strip()[2:] for ln in out.splitlines() if ln.strip().startswith("- ")]


def _diags(out: str) -> list[dict]:
    """The diagnostics Phase E emitted, decoded from the harness's dump."""
    line = next(
        (ln for ln in out.splitlines() if ln.startswith("DIAGS_JSON=")), None
    )
    assert line is not None, f"harness emitted no diagnostics dump:\n{out}"
    import json as _json

    return _json.loads(line[len("DIAGS_JSON="):])


def _codes(out: str) -> list[str]:
    return [d["code"] for d in _diags(out)]


# --------------------------------------------------------------- ordering ---

def test_phase_e_decides_before_phase_b_imports():
    """The gate's exit must precede the import it is gating.

    This is the trap the whole phase exists to avoid: a scan left in Phase D's
    position runs after ``from transform.main import ...`` and after
    ``ingest(...)``, so the model call has already happened when the check says
    no. Asserted on offsets in the shipped script, not on prose about it.
    """
    body = _script_body()
    gate_exit = body.index("PHASE E FAILED")
    phase_b = body.index("Phase B ---")
    # rindex for the Phase B call sites: Phase E's own comment quotes
    # `sys.path.insert(0, ".")` when it explains why it sits above them, and a
    # first-match index would compare the gate against its own prose.
    path_insert = body.rindex('sys.path.insert(0, ".")')
    transform_import = body.rindex("from transform.main import")
    ingest_call = body.rindex("ingest(duckdb=out")

    assert gate_exit < phase_b, "Phase E must be declared above the Phase B banner"
    assert gate_exit < path_insert, "Phase E must exit before sys.path is primed"
    assert gate_exit < transform_import, (
        "Phase E must decide BEFORE transform.main is imported — after it, the "
        "module body has already run"
    )
    assert gate_exit < ingest_call, (
        "Phase E must decide BEFORE ingest() runs — after it, 'denied' is a "
        "report about money already spent"
    )


def test_phase_e_exit_precedes_the_transform_import_structurally():
    """The exit CALL itself — not just the banner — comes before the import.

    ``test_phase_e_decides_before_phase_b_imports`` anchors on the "PHASE E
    FAILED" string, which is the message, not the mechanism. A block that printed
    the banner and fell through would satisfy it while gating nothing. This one
    locates the exit call inside Phase E's own failure branch and requires it
    above the import it exists to prevent.

    The call is ``finish(1)``, not ``sys.exit(1)``: every exit in the script now
    routes through ``finish`` so the diagnostic report and the build record are
    written on the way out. That indirection is exactly why this test also
    asserts ``finish`` terminates — a ``finish`` that returned would turn every
    gate in the script into a printed opinion, and this test would still pass on
    the call site alone.
    """
    body = _script_body()
    gate_branch = body.index("if eerrors:")
    gate_exit = body.index("finish(1)", gate_branch)
    transform_import = body.rindex("from transform.main import")

    assert gate_exit < transform_import, (
        "Phase E's finish(1) must appear before `from transform.main import` — "
        "without the exit, a denied closure prints a red banner and then runs "
        "the transform anyway"
    )

    # `finish` is the only thing standing between the banner and the import, so
    # its terminating behaviour is part of THIS gate's contract, not an unrelated
    # helper's business.
    finish_def = body.index("def finish(exit_code):")
    finish_end = body.index("\n# ---", finish_def)
    assert "sys.exit(exit_code)" in body[finish_def:finish_end], (
        "finish() must terminate. If it ever returns, Phase E's finish(1) stops "
        "gating anything and the transform is imported regardless."
    )


def test_phase_a_still_runs_first():
    """Phase E reads spec.py's service refs; Phase A is what validates them."""
    body = _script_body()
    assert body.index("phase A ok") < body.index("eerrors = []")


# ------------------------------------------------------- model-provider SDK ---

def test_model_sdk_import_fails_on_csv_closure(tmp_path):
    out = _run_phase_e(tmp_path, CSV, CLEAN_CSV_TRANSFORM + "import anthropic\n", expect_exit=1)
    assert "PHASE E FAILED" in out
    assert "model-provider SDK" in out
    assert "never calls a model" in out


def test_model_sdk_submodule_import_fails_once(tmp_path):
    """``from openai import OpenAI`` is one violation, not two.

    The AST yields both ``openai`` and ``openai.OpenAI``; reporting each would
    make a single bad import read as a pattern.
    """
    out = _run_phase_e(tmp_path, CSV, CLEAN_CSV_TRANSFORM + "from openai import OpenAI\n", expect_exit=1)
    assert "PHASE E FAILED" in out
    assert len(_findings(out)) == 1, _findings(out)
    assert "'openai'" in out


def test_dotted_model_root_is_matched(tmp_path):
    """``google.generativeai`` is denied; bare ``google`` is not the root."""
    out = _run_phase_e(
        tmp_path, CSV, CLEAN_CSV_TRANSFORM + "import google.generativeai as genai\n", expect_exit=1
    )
    assert "PHASE E FAILED" in out
    assert "google.generativeai" in out


def test_from_google_import_genai_is_matched(tmp_path):
    """``from google import genai`` is the current Google SDK spelling.

    It arrives as module="google", names=["genai"] — and NEITHER part is a denied
    root on its own, because denying bare ``google`` would take out
    ``google.cloud.storage`` and every other unrelated Google package. The gate
    catches it only because the ImportFrom expansion emits the joined
    ``google.genai``. A reader who "simplifies" that expansion away reopens the
    hole silently, so it is pinned here.
    """
    out = _run_phase_e(
        tmp_path, CSV, CLEAN_CSV_TRANSFORM + "from google import genai\n", expect_exit=1
    )
    assert "PHASE E FAILED" in out
    assert "google.genai" in out


def test_bare_google_package_is_not_collateral(tmp_path):
    """The other half of the same rule: ``google`` itself is not denied."""
    out = _run_phase_e(
        tmp_path, CSV,
        CLEAN_CSV_TRANSFORM + "from google.cloud import storage\n", expect_exit=0
    )
    assert "phase E ok" in out


def test_every_listed_model_root_is_denied(tmp_path):
    """Each root in MODEL_ROOTS actually fires.

    A deny list is only as good as its entries, and an entry that never matches
    any real import spelling is decoration. Each case here is the spelling an
    author would actually write.
    """
    for imp, shown in (
        ("import litellm\n", "litellm"),
        ("from litellm import completion\n", "litellm"),
        ("import groq\n", "groq"),
        ("from groq import Groq\n", "groq"),
        ("import together\n", "together"),
        ("import replicate\n", "replicate"),
        ("from huggingface_hub import InferenceClient\n", "huggingface_hub"),
        ("import vertexai\n", "vertexai"),
        ("from vertexai.generative_models import GenerativeModel\n", "vertexai"),
        ("from langchain_anthropic import ChatAnthropic\n", "langchain_anthropic"),
        ("from langchain_openai import ChatOpenAI\n", "langchain_openai"),
        ("from llama_index.core import VectorStoreIndex\n", "llama_index"),
        ("from anthropic_bedrock import AnthropicBedrock\n", "anthropic_bedrock"),
        ("import mistralai\n", "mistralai"),
        ("import ollama\n", "ollama"),
        ("import cohere\n", "cohere"),
    ):
        out = _run_phase_e(tmp_path, CSV, CLEAN_CSV_TRANSFORM + imp, expect_exit=1)
        assert "model-provider SDK" in out, imp
        assert shown in out, imp


def test_model_sdk_denied_even_when_no_connector_parses(tmp_path):
    """The SDK denial is waived by nothing — not even an unreadable spec.py.

    The transport check degrades to a warning when the declaration cannot be
    read (see ``test_unparseable_spec_warns_and_does_not_deny_transport``). The
    inference denial must NOT degrade with it: no state of spec.py licenses
    calling a model from a transform.
    """
    out = _run_phase_e(
        tmp_path, "def broken(:\n", CLEAN_CSV_TRANSFORM + "import anthropic\n",
        expect_exit=1,
    )
    assert "model-provider SDK" in out


def test_model_sdk_is_not_waived_by_a_declared_api_source(tmp_path):
    """The connector exception covers transport, never inference.

    An api-source closure legitimately opens sockets. It still may not call a
    model — declaring a connector is not a licence to infer inside the transform.
    """
    out = _run_phase_e(
        tmp_path, API,
        "from dlt.sources.rest_api import rest_api_source\nimport anthropic\n", expect_exit=1
    )
    assert "PHASE E FAILED" in out
    assert "model-provider SDK" in out


# ------------------------------------------------------------ import reach ---

def test_raw_transport_fails_on_csv_closure(tmp_path):
    out = _run_phase_e(tmp_path, CSV, CLEAN_CSV_TRANSFORM + "import requests\n", expect_exit=1)
    assert "PHASE E FAILED" in out
    assert "raw network transport" in out


def test_stdlib_transport_roots_are_denied(tmp_path):
    """urllib.request, socket and http.client are the stdlib escape hatches."""
    for imp, root in (
        ("import urllib.request\n", "urllib.request"),
        ("import socket\n", "socket"),
        ("from http.client import HTTPSConnection\n", "http.client"),
        ("import urllib3\n", "urllib3"),
    ):
        out = _run_phase_e(tmp_path, CSV, CLEAN_CSV_TRANSFORM + imp, expect_exit=1)
        assert "PHASE E FAILED" in out, imp
        assert root in out, imp


def test_transport_is_waived_for_a_declared_api_source(tmp_path):
    """dlt's REST source IS httpx and requests.

    A gate that fires on every correct api-source closure gets deleted rather
    than obeyed, so the waiver is load-bearing, not a loophole.
    """
    out = _run_phase_e(
        tmp_path, API,
        "import dlt\n"
        "from dlt.sources.rest_api import rest_api_resources, RESTAPIConfig\n"
        "import requests\nimport httpx\n", expect_exit=0
    )
    assert "phase E ok" in out
    assert "PHASE E FAILED" not in out


def test_transport_is_waived_for_a_declared_db_source(tmp_path):
    out = _run_phase_e(
        tmp_path, DB,
        "import dlt\nfrom dlt.sources.sql_database import sql_database\nimport socket\n", expect_exit=0
    )
    assert "phase E ok" in out


def test_labelled_multi_source_service_still_declares_its_type(tmp_path):
    """``api-source-github`` is an api-source (reference/multi-source.md)."""
    out = _run_phase_e(
        tmp_path, API_LABELLED,
        "from dlt.sources.rest_api import rest_api_source\nimport httpx\n", expect_exit=0
    )
    assert "phase E ok" in out


def test_transport_with_no_source_declared_fails(tmp_path):
    out = _run_phase_e(tmp_path, NO_SOURCE, CLEAN_CSV_TRANSFORM + "import requests\n", expect_exit=1)
    assert "PHASE E FAILED" in out
    assert "no connector service" in out


# ------------------------------------------- reading the declaration itself ---
# The waiver is the permissive branch of this gate, so how `declared_sources` is
# built is a security question, not a parsing detail. These pin the reader.

def test_a_commented_out_service_ref_grants_no_waiver(tmp_path):
    """A comment must not declare a connector.

    The original reader was ``re.findall`` over spec.py's SOURCE TEXT, so a
    spec.py whose only occurrence of api-source was inside a ``#`` comment
    declared api-source — and collected the transport waiver from a line Python
    never evaluates. Anyone able to type a comment could turn the gate off.
    Reading ``ast.Constant`` nodes is what closes it.

    The commented ref sits alongside a REAL csv-source declaration, because that
    is the shape that must deny: a closure whose readable declaration says "no
    network" and whose comment says otherwise. (A spec.py with ONLY the comment
    declares nothing readable at all and takes the warn path instead — see
    ``test_spec_with_no_service_reference_at_all_warns``. Both are correct; the
    distinction is between "declared non-network" and "unreadable".)
    """
    spec = (
        '_csv = "/infra-profile/desktop-local#/services/csv-source"\n'
        "# I could have used "
        '"/infra-profile/desktop-local#/services/api-source" here\n'
    )
    out = _run_phase_e(tmp_path, spec, CLEAN_CSV_TRANSFORM + "import requests\n",
                       expect_exit=1)
    assert "PHASE E FAILED" in out
    assert "raw network transport" in out
    # The comment must not reach the DECLARED SET the message reports. Asserted
    # on the rendered list rather than on the substring: the remediation text
    # legitimately says "declare an api-source", so a bare `not in out` would
    # fail on the fix advice instead of on the defect.
    assert "declares ['csv-source']" in out


def test_a_docstring_mentioning_a_service_grants_no_waiver(tmp_path):
    """A module docstring IS an ast.Constant — but not a service reference.

    The match is anchored on the whole string value, so prose that merely
    contains the path does not declare it. Without the anchor, moving from regex
    to AST would have swapped one text-shaped hole for another.
    """
    spec = (
        '"""This closure reads CSVs. It does not use '
        '/infra-profile/desktop-local#/services/api-source."""\n'
        '_csv = "/infra-profile/desktop-local#/services/csv-source"\n'
    )
    out = _run_phase_e(tmp_path, spec, CLEAN_CSV_TRANSFORM + "import requests\n",
                       expect_exit=1)
    assert "raw network transport" in out


def test_single_quoted_service_ref_is_read(tmp_path):
    """Quote style is not a declaration. The old regex only matched double."""
    spec = "_api = '/infra-profile/desktop-local#/services/api-source'\n"
    out = _run_phase_e(tmp_path, spec, CLEAN_CSV_TRANSFORM + "import httpx\n",
                       expect_exit=0)
    assert "phase E ok" in out
    assert "api-source" in out


def test_absolute_https_service_ref_is_read(tmp_path):
    """The platform accepts the absolute form too; so must this reader."""
    spec = ('_api = "https://nxd.example.com/infra-profile/desktop-local'
            '#/services/api-source"\n')
    out = _run_phase_e(tmp_path, spec, CLEAN_CSV_TRANSFORM + "import httpx\n",
                       expect_exit=0)
    assert "phase E ok" in out
    assert "api-source" in out


def test_absolute_https_csv_source_still_denies_transport(tmp_path):
    """The absolute form is read for DENIAL too, not only for the waiver.

    Reading a new spelling only where it grants permission would be worse than
    not reading it at all.
    """
    spec = ('_csv = "https://nxd.example.com/infra-profile/desktop-local'
            '#/services/csv-source"\n')
    out = _run_phase_e(tmp_path, spec, CLEAN_CSV_TRANSFORM + "import requests\n",
                       expect_exit=1)
    assert "raw network transport" in out
    assert "csv-source" in out


def test_unparseable_spec_warns_and_does_not_deny_transport(tmp_path):
    """No readable declaration is "unknown", not "declared nothing".

    Treating an unreadable spec.py as a closure that declared no connector denies
    every transport on the strength of a parse failure — a verdict this gate has
    not earned, and one whose message ("spec.py declares no connector service")
    would send the author looking for a declaration that is right there. Phase A
    owns the syntax error; here it is a warning.
    """
    out = _run_phase_e(tmp_path, "def broken(:\n",
                       CLEAN_CSV_TRANSFORM + "import requests\n", expect_exit=0)
    assert "warning:" in out
    assert "connector type is unknown" in out
    assert "PHASE E FAILED" not in out


def test_spec_with_no_service_reference_at_all_warns(tmp_path):
    """Parses fine, declares nothing readable — same "unknown", same warning."""
    out = _run_phase_e(tmp_path, "X = 1\n",
                       CLEAN_CSV_TRANSFORM + "import requests\n", expect_exit=0)
    assert "warning:" in out
    assert "phase E ok" in out


# --------------------------------------------------------- connector shape ---

def test_rest_api_import_on_csv_closure_is_a_shape_mismatch(tmp_path):
    """The closure reads from a source its own spec.py does not name."""
    out = _run_phase_e(
        tmp_path, CSV,
        CLEAN_CSV_TRANSFORM
        + "from dlt.sources.rest_api import rest_api_resources, RESTAPIConfig\n", expect_exit=1
    )
    assert "PHASE E FAILED" in out
    assert "a REST API source" in out
    assert "does not name" in out


def test_sql_database_import_on_csv_closure_is_a_shape_mismatch(tmp_path):
    out = _run_phase_e(
        tmp_path, CSV,
        CLEAN_CSV_TRANSFORM + "from dlt.sources.sql_database import sql_database\n", expect_exit=1
    )
    assert "PHASE E FAILED" in out
    assert "a database source" in out


def test_multi_source_closure_declaring_both_passes(tmp_path):
    """Declaring csv-source AND api-source licenses both shapes."""
    out = _run_phase_e(
        tmp_path, CSV + API,
        "from dlt.sources.rest_api import rest_api_source\n"
        "from dlt.sources.filesystem import filesystem\n"
        "import requests\n", expect_exit=0
    )
    assert "phase E ok" in out


# ------------------------------------------------------ no false positives ---

def test_clean_csv_closure_passes(tmp_path):
    out = _run_phase_e(tmp_path, CSV, CLEAN_CSV_TRANSFORM, expect_exit=0)
    assert "phase E ok" in out
    assert "PHASE E FAILED" not in out


def test_clean_file_source_closure_passes(tmp_path):
    out = _run_phase_e(tmp_path, FILE, CLEAN_CSV_TRANSFORM, expect_exit=0)
    assert "phase E ok" in out


def test_mcp_is_never_flagged(tmp_path):
    """``mcp`` ships in the fixed desktop venv and is not a denied root.

    Flagging it would fail closures that do nothing wrong, which is how a gate
    earns a blanket waiver from the next author.
    """
    out = _run_phase_e(
        tmp_path, CSV, CLEAN_CSV_TRANSFORM + "import mcp\nfrom mcp.server import Server\n", expect_exit=0
    )
    assert "phase E ok" in out


def test_prefix_collisions_are_not_collateral(tmp_path):
    """Denied roots match on dot boundaries.

    ``socketserver`` is not ``socket`` and ``requests_oauthlib`` is not
    ``requests``; a substring match would fail both.
    """
    out = _run_phase_e(
        tmp_path, CSV,
        CLEAN_CSV_TRANSFORM + "import socketserver\nimport requests_oauthlib\n", expect_exit=0
    )
    assert "phase E ok" in out


def test_relative_import_does_not_crash(tmp_path):
    """``from . import helpers`` has module=None/level=1 — must not blow up."""
    out = _run_phase_e(tmp_path, CSV, CLEAN_CSV_TRANSFORM + "from . import helpers\n", expect_exit=0)
    assert "phase E ok" in out


def test_no_environ_credential_check(tmp_path):
    """A closure reading os.environ is NOT a Phase E finding, by decision.

    The real credential channel is the ``.secrets([...])`` binding the platform
    resolves, so an environ scan watches a door nobody uses — and widening it to
    ``secrets[...]`` subscripts false-positives on every legitimate REST closure.
    Pinned so a later author does not "complete" the gate by adding it back.
    """
    out = _run_phase_e(
        tmp_path, CSV,
        CLEAN_CSV_TRANSFORM + "TOKEN = os.environ['SOME_TOKEN']\n", expect_exit=0
    )
    assert "phase E ok" in out


# ----------------------------------------------------- the scope boundary ---
# These closures PASS, and that is the finding. Each is a real way to reach the
# network that no import-level check can see. They are pinned as passing so the
# limit stays documented in executable form: a green Phase E is not proof the
# transform is offline.

def test_wrapped_socket_is_invisible(tmp_path):
    """Semantic detection is an explicit non-goal.

    A helper that opens a socket behind a local name defeats a name check. Phase
    E does not follow imports and does not reason about what a function does.
    """
    out = _run_phase_e(
        tmp_path, CSV, CLEAN_CSV_TRANSFORM + "from .net_helper import fetch\n", expect_exit=0
    )
    assert "phase E ok" in out, (
        "if this now fails, Phase E grew semantic detection — update the "
        "'What Phase E cannot see' section rather than just this assertion"
    )


def test_url_handed_to_a_reader_is_invisible(tmp_path):
    """pandas.read_json(url) and DuckDB httpfs are out of scope and unfixable here."""
    out = _run_phase_e(
        tmp_path, CSV,
        CLEAN_CSV_TRANSFORM
        + "import pandas as pd\n"
        + "df = pd.read_json('https://example.invalid/data.json')\n"
        + "con.execute(\"INSTALL httpfs; SELECT * FROM 'https://example.invalid/x.csv'\")\n", expect_exit=0
    )
    assert "phase E ok" in out


def test_dynamic_import_is_invisible(tmp_path):
    """importlib builds the name at runtime; there is no ast.Import node."""
    out = _run_phase_e(
        tmp_path, CSV,
        CLEAN_CSV_TRANSFORM + "import importlib\nm = importlib.import_module('requests')\n", expect_exit=0
    )
    assert "phase E ok" in out


def test_a_forged_declaration_passes(tmp_path):
    """The connector type is agent-authored, so the shape check is self-consistency.

    Declaring ``api-source`` in spec.py waives the transport family whether or
    not the closure really has one. Phase E catches the closure that DRIFTED, not
    the one that lied — the same generation pass writes both files and nothing
    independent stamps either.
    """
    out = _run_phase_e(tmp_path, API, CLEAN_CSV_TRANSFORM + "import httpx\n", expect_exit=0)
    assert "phase E ok" in out


# ------------------------------------------------------ diagnostic codes ---
# The prose above is for the human reading the scrollback. The CODE is what the
# build record carries and what any consumer keys on, and the two are
# independent: a rule can fire with the right message and the wrong code, and
# every text assertion in this file would still pass. These pin the code.


def test_model_sdk_import_emits_its_code(tmp_path):
    out = _run_phase_e(
        tmp_path, CSV, CLEAN_CSV_TRANSFORM + "import anthropic\n", expect_exit=1
    )
    assert _codes(out) == ["reach.model_sdk_import"]


def test_undeclared_transport_emits_its_code(tmp_path):
    out = _run_phase_e(
        tmp_path, CSV, CLEAN_CSV_TRANSFORM + "import requests\n", expect_exit=1
    )
    assert _codes(out) == ["reach.undeclared_transport"]


def test_shape_mismatch_emits_its_code(tmp_path):
    out = _run_phase_e(
        tmp_path, CSV,
        CLEAN_CSV_TRANSFORM + "from dlt.sources.rest_api import rest_api_source\n",
        expect_exit=1,
    )
    assert _codes(out) == ["reach.connector_shape_mismatch"]


def test_unreadable_declaration_warns_with_its_code(tmp_path):
    """A warning, and the run still passes — the gate did not earn a denial."""
    out = _run_phase_e(
        tmp_path, "x = 1\n", CLEAN_CSV_TRANSFORM, expect_exit=0
    )
    assert _codes(out) == ["reach.connector_undeclared"]
    assert "phase E ok" in out


def test_every_reach_finding_lands_on_s1_structure(tmp_path):
    """Phase E must file under the stage it runs in, not Phase B's.

    ``s1_structure`` is offline and precedes the transform import. Filing a reach
    finding under ``s2_transform`` would say the transform ran — which is the one
    thing this gate exists to prevent.
    """
    out = _run_phase_e(
        tmp_path, CSV, CLEAN_CSV_TRANSFORM + "import anthropic\n", expect_exit=1
    )
    assert {d["stage"] for d in _diags(out)} == {"s1_structure"}


def test_reach_codes_are_registered_in_the_shared_vocabulary():
    """Every code Phase E emits must exist in the shared registry.

    ``test_self_check_diagnostic_vocab.py`` enforces this across the whole
    script by walking its string constants. Asserted again here, narrowly, so
    that deleting a ``reach.*`` code from the registry names THIS gate in the
    failure rather than a generic vocabulary drift.
    """
    import sys as _sys

    skill_scripts = EVALS_DIR.parent / "src" / "nxd-pocket-loop" / "scripts"
    if str(skill_scripts) not in _sys.path:
        _sys.path.insert(0, str(skill_scripts))
    import dp_diagnostics as dpd

    emitted = {
        "reach.model_sdk_import",
        "reach.undeclared_transport",
        "reach.connector_shape_mismatch",
        "reach.connector_undeclared",
    }
    missing = emitted - set(dpd.CODES)
    assert not missing, f"Phase E emits unregistered codes: {sorted(missing)}"

    for code in emitted:
        assert dpd.CODES[code]["stage"] == "s1_structure", code
        # Every reach finding is fixed by editing the closure. None is a question
        # for the user and none is environmental — an `owner` drift here would
        # silently reroute the finding away from the agent that can fix it.
        assert dpd.CODES[code]["owner"] == "agent", code


if __name__ == "__main__":  # pragma: no cover
    import pytest

    raise SystemExit(pytest.main([__file__, "-q"]))

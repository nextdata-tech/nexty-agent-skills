"""Terminal-only acceptance cases for the public field-mapper call adapter.

The mapper implementation is owned by the nxd package.  These scenarios keep
the generated-transform boundary honest from the skills repository: all input
and provider material is synthetic, no model SDK or network is involved, and
the assertions are based on the public callback shape documented in
``mapper/CONTRACT.md``.

They deliberately require a local nxd checkout.  CI for this repository is
air-gapped from that checkout, so the module skips there rather than claiming
that static skill text is an execution result.  See ``evals/tests/_harness.py``.
"""

from __future__ import annotations

import ast
import importlib.util
from collections.abc import Iterator
import json
import sys
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

from _harness import harness_path, requires_harness


REPO_ROOT = Path(__file__).resolve().parents[2]
CONTRACT = REPO_ROOT / "src/nxd-generate-data-product/mapper/CONTRACT.md"
E2E_RUNNER = REPO_ROOT / "src/nxd-generate-data-product/mapper/examples/e2e/run_e2e.py"
TERMINAL_SCENARIO = REPO_ROOT / "evals/public/terminal-field-mapper-adapter-contract"
SAMPLE = "samples/01-row-scores"
SCENARIO_CHECKS = json.loads((TERMINAL_SCENARIO / "checks.json").read_text(encoding="utf-8"))
SYNTHETIC_SECRET = SCENARIO_CHECKS["deterministic_check"]["redaction_markers"][0]


def _load_checker(name: str = "nex884_terminal_checker") -> Any:
    checker_path = TERMINAL_SCENARIO / "fixtures/check_terminal_mapper_adapter.py"
    spec = importlib.util.spec_from_file_location(name, checker_path)
    assert spec is not None and spec.loader is not None
    checker = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(checker)
    return checker


@pytest.fixture(scope="module")
def _import_canonical_harness() -> Iterator[None]:
    """Import exactly the nxd checkout selected by ``NXD_REPO``.

    ``harness_path`` is intentionally exclusive when NXD_REPO is set.  Adding
    that checkout's data-product root to ``sys.path`` makes imports resolve as
    they do for a locally installed nxd wheel, without copying a second mapper
    implementation into this skills repository.
    """
    path = harness_path()
    if path is None:
        pytest.skip("canonical nxd field-mapper harness is unavailable")
    package_root = path.parents[2]  # .../data_product, containing nxd/
    sys.path.insert(0, str(package_root))
    try:
        yield
    finally:
        sys.path.remove(str(package_root))
        for name in tuple(sys.modules):
            if name == "nxd" or name.startswith("nxd."):
                del sys.modules[name]


def _runtime() -> dict[str, Any]:
    from nxd.experimental.field_mapper import Grant
    from nxd.experimental.field_mapper import MapperInput
    from nxd.experimental.field_mapper import MapperSpec
    from nxd.experimental.field_mapper import make_call
    from nxd.experimental.field_mapper import map_inputs
    from nxd.experimental.field_mapper import __version__
    from nxd.experimental.field_mapper.errors import CredentialMissing
    from nxd.experimental.field_mapper.errors import TransportExhausted
    from nxd.experimental.field_mapper.schema import compile_schema

    harness = harness_path()
    assert harness is not None
    sample = harness / SAMPLE
    spec = MapperSpec.load(sample / "spec.json")
    bound = replace(spec.with_wire_schema(compile_schema(spec)), harness_version=__version__)
    grant = Grant.from_dict(
        {
            "mapper_spec_id": bound.mapper_spec_id,
            "provider": "anthropic",
            "model": spec.model,
            "purpose": "NEX-884 synthetic terminal adapter contract",
            "input_fields": ["ticket_id", "body"],
            "max_calls": 2,
            "max_tokens": 1000,
            "max_usd": 1.0,
        }
    )
    item = MapperInput(
        input_id="NEX-884-1",
        identity={"ticket_id": "NEX-884-1"},
        fields={"ticket_id": "NEX-884-1", "body": "outage"},
        landed_text="outage",
    )
    return {
        "grant": grant,
        "item": item,
        "make_call": make_call,
        "map_inputs": map_inputs,
        "spec": spec,
        "TransportExhausted": TransportExhausted,
        "CredentialMissing": CredentialMissing,
    }


def _mapped(runtime: dict[str, Any], tmp_path: Path, call: Any) -> Any:
    return runtime["map_inputs"](
        [runtime["item"]],
        spec=runtime["spec"],
        grant=runtime["grant"],
        run_dir=str(tmp_path / "run" / "mapper"),
        call=call,
        allow_unverified=False,
    )


@requires_harness
def test_public_adapter_constructs_the_documented_request_and_parses_response(
    _import_canonical_harness: None, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    runtime = _runtime()
    calls: list[dict[str, Any]] = []

    class FakeClient:
        def __init__(self, **kwargs: Any) -> None:
            # An explicit transform secret is the only credential fixture.  It
            # must reach the lazy client, but must not reach a mapper ledger.
            assert kwargs["api_key"] == SYNTHETIC_SECRET

        def call(self, **kwargs: Any) -> dict[str, Any]:
            calls.append(kwargs)
            evidence = [{"quote": "outage", "source_field_name": "body"}]
            return {
                "severity_score": {"value": 5, "evidence": evidence},
                "triage_verdict": {"value": "escalate", "evidence": evidence},
            }

    monkeypatch.setattr("nxd.experimental.field_mapper.transport.Client", FakeClient)
    call = runtime["make_call"](
        spec=runtime["spec"],
        grant=runtime["grant"],
        secrets={"anthropic_api_key": SYNTHETIC_SECRET},
        allow_env=False,
    )
    result = _mapped(runtime, tmp_path, call)

    assert len(calls) == 1
    assert calls[0]["input_hash"] == "NEX-884-1"
    assert set(calls[0]["wire_schema"]["required"]) == {"severity_score", "triage_verdict"}
    assert {proposal.value_status for proposal in result.proposals} == {"ok"}
    _assert_secret_absent(tmp_path)


@requires_harness
@pytest.mark.parametrize(("name", "expected_code"), [
    ("raw-provider-response", "schema_reject"),
    ("provider-error", "transport_exhausted"),
])
def test_adapter_failures_land_sanitized_machine_statuses(
    _import_canonical_harness: None, tmp_path: Path, name: str, expected_code: str
) -> None:
    runtime = _runtime()

    if name == "provider-error":
        def adapter(**_kwargs: Any) -> Any:
            raise runtime["TransportExhausted"]("synthetic provider unavailable")
    else:
        class RawSdkMessage:
            """SDK-like response: content exists, but no parsed JSON body."""

            content = "not valid JSON"
            parsed = None
            error_code = "schema_reject"
            error_detail = "provider returned invalid JSON"
            provider = "fixture"

        def adapter(**_kwargs: Any) -> Any:
            return RawSdkMessage()

    result = _mapped(runtime, tmp_path, adapter)
    assert {proposal.error_code for proposal in result.proposals} == {expected_code}
    assert all(proposal.value_status == "error" for proposal in result.proposals)
    _assert_secret_absent(tmp_path)


@requires_harness
def test_schema_invalid_structured_response_is_rejected_per_field(
    _import_canonical_harness: None, tmp_path: Path
) -> None:
    runtime = _runtime()

    def adapter(**_kwargs: Any) -> dict[str, Any]:
        # The compiled schema requires both target fields.  Returning only one
        # is a recorded-provider fixture, not a live model call.
        return {"severity_score": {"value": 5, "evidence": []}}

    result = _mapped(runtime, tmp_path, adapter)
    statuses = {proposal.field: proposal.error_code for proposal in result.proposals}
    assert statuses["triage_verdict"] == "schema_reject"
    _assert_secret_absent(tmp_path)


@requires_harness
def test_explicit_secret_wins_over_approved_environment_fallback(
    _import_canonical_harness: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = _runtime()
    created: list[dict[str, Any]] = []

    class FakeClient:
        def __init__(self, **kwargs: Any) -> None:
            created.append(kwargs)

        def call(self, **_kwargs: Any) -> dict[str, Any]:
            return {"severity_score": {"value": 5, "evidence": []}}

    monkeypatch.setenv("ANTHROPIC_API_KEY", "nex884-ambient-secret-must-lose")
    monkeypatch.setattr("nxd.experimental.field_mapper.transport.Client", FakeClient)
    call = runtime["make_call"](
        spec=runtime["spec"], grant=runtime["grant"],
        secrets={"anthropic_api_key": SYNTHETIC_SECRET}, allow_env=True,
    )
    from nxd.experimental.field_mapper.schema import compile_schema

    call(item=runtime["item"], spec=runtime["spec"], wire_schema=compile_schema(runtime["spec"]), violations=())
    assert created[0]["api_key"] == SYNTHETIC_SECRET


@requires_harness
def test_approved_environment_fallback_is_explicit_and_missing_credentials_are_sanitized(
    _import_canonical_harness: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = _runtime()
    created: list[dict[str, Any]] = []

    class FakeClient:
        def __init__(self, **kwargs: Any) -> None:
            created.append(kwargs)

        def call(self, **_kwargs: Any) -> dict[str, Any]:
            return {"severity_score": {"value": 5, "evidence": []}}

    monkeypatch.setenv("ANTHROPIC_API_KEY", SYNTHETIC_SECRET)
    monkeypatch.setattr("nxd.experimental.field_mapper.transport.Client", FakeClient)
    call = runtime["make_call"](
        spec=runtime["spec"], grant=runtime["grant"], allow_env=True,
    )
    from nxd.experimental.field_mapper.schema import compile_schema

    call(item=runtime["item"], spec=runtime["spec"], wire_schema=compile_schema(runtime["spec"]), violations=())
    assert created[0]["api_key"] == SYNTHETIC_SECRET

    # A closure-only caller has no ambient credential path, even when the
    # process itself contains one.  The error names the stable condition, not
    # the secret that happened to be present in the environment.
    blocked = runtime["make_call"](
        spec=runtime["spec"], grant=runtime["grant"], allow_env=False,
    )
    with pytest.raises(runtime["CredentialMissing"]) as raised:
        blocked(
            item=runtime["item"], spec=runtime["spec"],
            wire_schema=compile_schema(runtime["spec"]), violations=(),
        )
    assert SYNTHETIC_SECRET not in str(raised.value)


def test_generated_closure_uses_only_the_public_adapter_surface() -> None:
    """The shipped example is a generated-closure oracle, not a runtime import."""
    if not E2E_RUNNER.is_file():
        pytest.skip("mapper examples submodule not initialized")
    source = E2E_RUNNER.read_text(encoding="utf-8")
    tree = ast.parse(source)
    imports = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    } | {
        f"{node.module}.{alias.name}" if node.module else alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
        for alias in node.names
    }

    assert "nxd.experimental.field_mapper.make_call" in imports
    assert not any(name == "anthropic" or name.startswith("anthropic.") for name in imports)
    assert not any("field_mapper.transport" in name or "field_mapper.ledger" in name for name in imports)
    # Attribute probes such as ``proposal.__dict__`` and ``getattr(proposal,
    # ...)`` make generated code depend on an undocumented record shape.
    assert "getattr(proposal" not in source
    assert "proposal.__dict__" not in source


def test_generated_closure_negative_fixtures_use_the_shipped_checker() -> None:
    """Static closure defects are classified by the public checker itself."""
    checker = _load_checker("nex884_negative_checker")
    fixtures = {
        "absent-adapter": (
            "def transform():\n    return {}\n",
            {"public make_call call missing", "map_inputs call missing"},
        ),
        "direct-sdk": (
            "import anthropic\n",
            {"provider SDK import", "public make_call call missing", "map_inputs call missing"},
        ),
        "aliased-sdk": (
            "import anthropic as provider\n",
            {"provider SDK import", "public make_call call missing", "map_inputs call missing"},
        ),
        "private-transport": (
            "from nxd.experimental.field_mapper.transport import Client\n",
            {"private mapper import", "public make_call call missing", "map_inputs call missing"},
        ),
        "aliased-private-transport": (
            "from nxd.experimental.field_mapper import transport as mapper_transport\n",
            {"private mapper import", "public make_call call missing", "map_inputs call missing"},
        ),
        "raw-message": (
            "from anthropic.types import Message\n\ndef adapter(**kwargs):\n    return Message\n",
            {"provider SDK import", "raw provider response return", "public make_call call missing", "map_inputs call missing"},
        ),
        "multiple-returns": (
            "def f(flag):\n    if flag:\n        return response\n    return result\n",
            {"raw provider response return", "public make_call call missing", "map_inputs call missing"},
        ),
        "dynamic-sdk": (
            "import importlib\nimportlib.import_module(\"anthropic\")\n",
            {"provider SDK import", "public make_call call missing", "map_inputs call missing"},
        ),
    }
    for _name, (source, expected) in fixtures.items():
        assert set(checker.findings(source)) == expected

    aliased_public = (
        "import nxd.experimental.field_mapper as fm\n"
        "def run():\n"
        "    call = fm.make_call(spec=spec, grant=grant, allow_env=False)\n"
        "    return fm.map_inputs(inputs, spec=spec, grant=grant, call=call)\n"
    )
    assert checker.findings(aliased_public) == []
    from_submodule = (
        "from nxd.experimental import field_mapper as fm\n"
        "def run():\n"
        "    call = fm.make_call(spec=spec, grant=grant, allow_env=False)\n"
        "    return fm.map_inputs(inputs, spec=spec, grant=grant, call=call)\n"
    )
    assert checker.findings(from_submodule) == []


def test_contract_names_callback_shape_and_sanitized_boundaries() -> None:
    contract = " ".join(CONTRACT.read_text(encoding="utf-8").split())
    for required in ("`item`", "`spec`", "`wire_schema`", "`violations`"):
        assert required in contract
    for required in ("coroutine", "provider SDK", "transport.Client", "SDK response object",
                     "stable machine codes", "credentials"):
        assert required in contract


def test_terminal_evaluator_scenario_fails_closed_until_mcp_harness_exists() -> None:
    """Register the E2E in the existing terminal evaluator, not as pytest-only.

    The marker explains the missing runtime capability precisely.  The checker
    already rejects an ordinary shell transcript: it needs a public
    nxd-desktop MCP build/inspect trace, so enabling the scenario without the
    missing stdio harness cannot accidentally manufacture a passing result.
    """
    checks = SCENARIO_CHECKS
    assert checks["wants_trace"] is True
    assert checks["deterministic_check"]["wants_trace"] is True
    assert checks["deterministic_check"]["trace_source"] == "runner_mcp"
    assert "per-run nxd-desktop stdio MCP server" in checks["ci_skip"]
    assert "JSON-RPC trace sink" in checks["ci_skip"]
    assert '"terminal-field-mapper-adapter-contract": frozenset' in (
        REPO_ROOT / "evals/run.py"
    ).read_text(encoding="utf-8")

    checker = _load_checker()

    good = (
        "from nxd.experimental.field_mapper import make_call, map_inputs\n"
        "def run():\n"
        "    call = make_call(spec=spec, grant=grant, allow_env=False)\n"
        "    return map_inputs(inputs, spec=spec, grant=grant, run_dir=run_dir, call=call)\n"
    )
    assert checker.findings(good) == []
    assert "provider SDK import" in checker.findings("import anthropic as sdk\n")
    assert "private mapper import" in checker.findings(
        "from nxd.experimental.field_mapper import transport as hidden\n"
    )
    assert "raw provider response return" in checker.findings("def f():\n    return response\n")
    assert "provider SDK import" in checker.findings("import importlib\nimportlib.import_module(name)\n")
    assert "provider SDK import" in checker.findings("__import__(name)\n")
    assert "raw provider response return" in checker.findings("def f():\n    return self.response\n")
    assert "undocumented proposal attribute" in checker.findings(
        "def f():\n    return proposal.value\n"
    )
    assert "undocumented proposal attribute" not in checker.findings(
        "def f():\n    return proposal.value_status\n"
    )
    assert "undocumented proposal attribute" in checker.findings(
        "def f():\n    return getattr(proposal, name)\n"
    )
    assert "private mapper import" in checker.findings(
        "import nxd.experimental.field_mapper as fm\ngetattr(fm, name)\n"
    )
    assert "private mapper import" not in checker.findings(
        "getattr(row, column_name)\n"
    )
    assert "private mapper import" in checker.findings(
        'import nxd.experimental.field_mapper as fm\ngetattr(fm, "transport")\n'
    )
    assert "private mapper import" in checker.findings(
        'importlib.import_module("nxd.experimental.field_mapper.transport")\n'
    )

    assert checker.trace_errors("nxd-desktop build_data_product\n") == [
        "trace is not runner-authored JSON-RPC"
    ]
    good_trace = json.dumps({
        "source": "runner", "protocol": "mcp", "direction": "request",
        "method": "tools/call", "tool": "build_data_product",
    }) + "\n"
    assert checker.trace_errors(good_trace) == []


def test_terminal_checker_redacts_secret_bearing_trace_and_artifact(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A checker failure must name the class, never replay its secret input."""
    checker = _load_checker("nex884_redaction_checker")

    main = tmp_path / "transform/main.py"
    main.parent.mkdir()
    main.write_text(
        "from nxd.experimental.field_mapper import make_call, map_inputs\n"
        "def run():\n"
        "    call = make_call(spec=spec, grant=grant, "
        "secrets={\"anthropic_api_key\": provided_secret}, allow_env=False)\n"
        "    return map_inputs(inputs, spec=spec, grant=grant, run_dir=run_dir, call=call)\n",
        encoding="utf-8",
    )
    (tmp_path / "run").mkdir()
    mixed_case_secret = "Opaque-Secret-7F8b92"
    (tmp_path / "run/ledger.json").write_text(mixed_case_secret, encoding="utf-8")
    trace = tmp_path.parent / f"{tmp_path.name}-trace.jsonl"
    trace.write_text(
        json.dumps({
            "source": "runner", "protocol": "mcp", "direction": "request",
            "method": "tools/call", "tool": "build_data_product",
            "detail": mixed_case_secret,
        }) + "\n",
        encoding="utf-8",
    )
    marker_file = tmp_path.parent / f"{tmp_path.name}-markers.txt"
    marker_file.write_text(mixed_case_secret + "\n", encoding="utf-8")
    monkeypatch.setattr(
        sys, "argv", ["checker", "--fixtures", str(TERMINAL_SCENARIO / "fixtures"),
                        "--root", str(tmp_path), "--trace", str(trace),
                        "--secret-marker-file", str(marker_file)],
    )

    assert checker.main() == 1
    output = capsys.readouterr().out
    assert "credential material appears in artifact" in output
    assert "credential material appears in trace" in output
    assert mixed_case_secret not in output
    assert "anthropic_api_key" not in output

    monkeypatch.setattr(
        sys, "argv", ["checker", "--fixtures", str(TERMINAL_SCENARIO / "fixtures"),
                        "--root", str(tmp_path), "--trace", str(trace)],
    )
    assert checker.main() == 1
    assert "redaction markers are required" in capsys.readouterr().out


def _assert_secret_absent(root: Path) -> None:
    """Fail if a test artifact/ledger contains our synthetic credential."""
    for path in root.rglob("*"):
        if path.is_file():
            assert SYNTHETIC_SECRET not in path.read_text(encoding="utf-8", errors="ignore"), path

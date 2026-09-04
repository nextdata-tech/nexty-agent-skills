"""Deterministic tests for the semantic MCP contract checker.

No network, no wheels, no NXD install: every case builds its two surfaces
inline. The one test that reads real files reads the COMMITTED exceptions file
against a synthetic pair, so it pins the exceptions this repository actually
ships without pinning a contract it does not own.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

import contract_check
from contract_check import ContractCheckError
from contract_check import check
from contract_check import load_contract_document
from contract_check import load_exceptions
from contract_check import load_surface_document


def _tool(name: str, parameters: dict[str, bool]) -> dict[str, Any]:
    return {
        "name": name,
        "description_segments": [f"{name} does a thing."],
        "description_is_exact": True,
        "input_schema": {"type": "object", "properties": {key: {} for key in parameters}},
        "parameters": [{"name": key, "required": value} for key, value in sorted(parameters.items())],
    }


def _typed_tool(name: str, parameter_type: str) -> dict[str, Any]:
    tool = _tool(name, {"value": True})
    tool["input_schema"]["properties"]["value"] = {"type": parameter_type}
    return tool


def _typed_surface_tool(name: str, parameter_type: str) -> dict[str, Any]:
    tool = _surface_tool(name, {"value": True})
    tool["input_schema"]["properties"]["value"] = {"type": parameter_type}
    return tool


def _surface_tool(name: str, parameters: dict[str, bool]) -> dict[str, Any]:
    return {
        "name": name,
        "description": f"eval paraphrase of {name}",
        "input_schema": {"type": "object", "properties": {key: {} for key in parameters}},
        "parameters": [{"name": key, "required": value} for key, value in sorted(parameters.items())],
    }


def _contract(*tools: dict[str, Any]) -> dict[str, Any]:
    return {"schema": contract_check.CONTRACT_SCHEMA, "tools": list(tools)}


def _surface(*tools: dict[str, Any]) -> dict[str, Any]:
    return {"schema": contract_check.SURFACE_SCHEMA, "tools": list(tools)}


def _exceptions(**kwargs: Any) -> dict[str, Any]:
    document: dict[str, Any] = {"schema": contract_check.EXCEPTIONS_SCHEMA}
    document.update(kwargs)
    return document


def _kinds(findings: list[contract_check.Finding]) -> list[tuple[str, str, str | None]]:
    return [(finding.kind, finding.tool, finding.parameter) for finding in findings]


class TestConformance:
    def test_identical_surfaces_are_clean(self) -> None:
        tools = _contract(_tool("run", {"measures": True}))
        surface = _surface(_surface_tool("run", {"measures": True}))
        assert check(tools, surface, _exceptions()) == []

    def test_no_exceptions_key_is_treated_as_no_exceptions(self) -> None:
        """A minimal exceptions file must not be read as a blanket waiver."""
        contract = _contract(_tool("run", {}), _tool("gone", {}))
        surface = _surface(_surface_tool("run", {}))
        assert _kinds(check(contract, surface, _exceptions())) == [("missing-tool", "gone", None)]


class TestUndeclaredDifferencesFail:
    def test_a_production_tool_missing_from_the_eval_fails(self) -> None:
        contract = _contract(_tool("run", {}), _tool("semantic_model", {}))
        surface = _surface(_surface_tool("run", {}))
        assert _kinds(check(contract, surface, _exceptions())) == [("missing-tool", "semantic_model", None)]

    def test_an_eval_tool_production_lacks_fails(self) -> None:
        contract = _contract(_tool("run", {}))
        surface = _surface(_surface_tool("run", {}), _surface_tool("invented", {}))
        assert _kinds(check(contract, surface, _exceptions())) == [("unexplained-tool", "invented", None)]

    def test_a_production_parameter_missing_from_the_eval_fails(self) -> None:
        contract = _contract(_tool("run", {"measures": True, "limit": False}))
        surface = _surface(_surface_tool("run", {"measures": True}))
        assert _kinds(check(contract, surface, _exceptions())) == [("missing-parameter", "run", "limit")]

    def test_an_eval_parameter_production_lacks_fails(self) -> None:
        contract = _contract(_tool("run", {"measures": True}))
        surface = _surface(_surface_tool("run", {"measures": True, "raw_sql": False}))
        assert _kinds(check(contract, surface, _exceptions())) == [("unexplained-parameter", "run", "raw_sql")]

    def test_a_required_ness_difference_fails(self) -> None:
        contract = _contract(_tool("run", {"measures": True}))
        surface = _surface(_surface_tool("run", {"measures": False}))
        findings = check(contract, surface, _exceptions())
        assert _kinds(findings) == [("parameter-requiredness", "run", "measures")]
        assert "production treats it as required" in findings[0].detail

    def test_a_parameter_schema_difference_fails(self) -> None:
        contract = _contract(_typed_tool("run", "string"))
        surface = _surface(_typed_surface_tool("run", "integer"))
        assert _kinds(check(contract, surface, _exceptions())) == [("parameter-schema", "run", "value")]

    def test_every_undeclared_difference_is_reported_not_just_the_first(self) -> None:
        """One fix per run would hide the rest behind a green-after-one-fix loop."""
        contract = _contract(_tool("run", {"measures": True, "limit": False}), _tool("gone", {}))
        surface = _surface(_surface_tool("run", {"measures": False, "raw_sql": False}), _surface_tool("invented", {}))
        assert sorted(_kinds(check(contract, surface, _exceptions()))) == sorted(
            [
                ("missing-tool", "gone", None),
                ("unexplained-tool", "invented", None),
                ("missing-parameter", "run", "limit"),
                ("unexplained-parameter", "run", "raw_sql"),
                ("parameter-requiredness", "run", "measures"),
            ]
        )


class TestDeclaredExceptionsPass:
    def test_a_declared_missing_tool_passes(self) -> None:
        contract = _contract(_tool("run", {}), _tool("semantic_model", {}))
        surface = _surface(_surface_tool("run", {}))
        exceptions = _exceptions(missing_tools=[{"name": "semantic_model", "reason": "not graded"}])
        assert check(contract, surface, exceptions) == []

    def test_a_declared_missing_parameter_passes(self) -> None:
        contract = _contract(_tool("run", {"measures": True, "limit": False}))
        surface = _surface(_surface_tool("run", {"measures": True}))
        exceptions = _exceptions(missing_parameters=[{"tool": "run", "parameter": "limit", "reason": "executor caps"}])
        assert check(contract, surface, exceptions) == []

    def test_a_declared_extra_parameter_passes(self) -> None:
        contract = _contract(_tool("run", {"measures": True}))
        surface = _surface(_surface_tool("run", {"measures": True, "debug": False}))
        exceptions = _exceptions(extra_parameters=[{"tool": "run", "parameter": "debug", "reason": "harness only"}])
        assert check(contract, surface, exceptions) == []

    def test_a_declared_required_ness_mismatch_passes(self) -> None:
        contract = _contract(_tool("run", {"measures": False}))
        surface = _surface(_surface_tool("run", {"measures": True}))
        exceptions = _exceptions(
            parameter_mismatches=[{"tool": "run", "parameter": "measures", "reason": "eval is stricter"}]
        )
        assert check(contract, surface, exceptions) == []

    def test_a_required_ness_exception_does_not_waive_a_type_change(self) -> None:
        contract = _contract(_typed_tool("run", "string"))
        surface = _surface(_typed_surface_tool("run", "integer"))
        surface["tools"][0]["parameters"][0]["required"] = False
        exceptions = _exceptions(
            parameter_mismatches=[{"tool": "run", "parameter": "value", "reason": "eval is stricter"}]
        )
        assert _kinds(check(contract, surface, exceptions)) == [("parameter-schema", "run", "value")]

    def test_an_exception_does_not_waive_a_different_difference(self) -> None:
        """A declared entry must be scoped to what it names, nothing adjacent."""
        contract = _contract(_tool("run", {"measures": True, "limit": False, "order_by": False}))
        surface = _surface(_surface_tool("run", {"measures": True}))
        exceptions = _exceptions(missing_parameters=[{"tool": "run", "parameter": "limit", "reason": "executor caps"}])
        assert _kinds(check(contract, surface, exceptions)) == [("missing-parameter", "run", "order_by")]


class TestStaleExceptionsFail:
    def test_a_missing_tool_exception_fails_once_the_eval_has_the_tool(self) -> None:
        contract = _contract(_tool("run", {}), _tool("semantic_model", {}))
        surface = _surface(_surface_tool("run", {}), _surface_tool("semantic_model", {}))
        exceptions = _exceptions(missing_tools=[{"name": "semantic_model", "reason": "not graded"}])
        assert _kinds(check(contract, surface, exceptions)) == [("stale-exception", "semantic_model", None)]

    def test_a_missing_tool_exception_fails_once_production_drops_the_tool(self) -> None:
        contract = _contract(_tool("run", {}))
        surface = _surface(_surface_tool("run", {}))
        exceptions = _exceptions(missing_tools=[{"name": "semantic_model", "reason": "not graded"}])
        assert _kinds(check(contract, surface, exceptions)) == [("stale-exception", "semantic_model", None)]

    def test_a_missing_parameter_exception_fails_once_the_eval_accepts_it(self) -> None:
        contract = _contract(_tool("run", {"measures": True, "limit": False}))
        surface = _surface(_surface_tool("run", {"measures": True, "limit": False}))
        exceptions = _exceptions(missing_parameters=[{"tool": "run", "parameter": "limit", "reason": "executor caps"}])
        assert _kinds(check(contract, surface, exceptions)) == [("stale-exception", "run", "limit")]

    def test_a_required_ness_exception_fails_once_the_two_agree(self) -> None:
        contract = _contract(_tool("run", {"measures": True}))
        surface = _surface(_surface_tool("run", {"measures": True}))
        exceptions = _exceptions(
            parameter_mismatches=[{"tool": "run", "parameter": "measures", "reason": "eval is stricter"}]
        )
        assert _kinds(check(contract, surface, exceptions)) == [("stale-exception", "run", "measures")]


class TestFailClosedInputs:
    def test_a_missing_contract_file_is_an_error_not_an_empty_contract(self, tmp_path: Path) -> None:
        with pytest.raises(ContractCheckError, match="unreadable"):
            load_contract_document(tmp_path / "absent.json")

    def test_malformed_json_is_an_error(self, tmp_path: Path) -> None:
        path = tmp_path / "contract.json"
        path.write_text("{not json", encoding="utf-8")
        with pytest.raises(ContractCheckError, match="not valid JSON"):
            load_contract_document(path)

    def test_a_wrong_schema_is_refused(self, tmp_path: Path) -> None:
        path = tmp_path / "contract.json"
        path.write_text(json.dumps({"schema": "something-else", "tools": []}), encoding="utf-8")
        with pytest.raises(ContractCheckError, match="nxd-semantic-mcp-contract-v1"):
            load_contract_document(path)

    def test_a_surface_document_is_not_accepted_as_a_contract(self, tmp_path: Path) -> None:
        """The two documents are shaped alike; only the schema tells them apart."""
        path = tmp_path / "mixed.json"
        path.write_text(json.dumps(_surface(_surface_tool("run", {}))), encoding="utf-8")
        with pytest.raises(ContractCheckError):
            load_contract_document(path)
        assert load_surface_document(path)["tools"][0]["name"] == "run"

    def test_an_uninstalled_nxd_is_an_error_not_a_skip(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """A job with no NXD artifact must fail, never pass vacuously."""
        import builtins

        real_import = builtins.__import__

        def _refuse(name: str, *args: Any, **kwargs: Any) -> Any:
            if name.startswith("nxd."):
                raise ImportError("no nxd here")
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", _refuse)
        with pytest.raises(ContractCheckError, match="not importable"):
            contract_check.load_installed_contract()


class TestCommittedExceptionsFile:
    def test_it_parses_and_declares_a_reason_for_every_entry(self) -> None:
        exceptions = load_exceptions()
        entries = [
            *exceptions.get("missing_tools", []),
            *exceptions.get("extra_tools", []),
            *exceptions.get("missing_parameters", []),
            *exceptions.get("extra_parameters", []),
            *exceptions.get("parameter_mismatches", []),
        ]
        assert entries, "the committed exceptions file declares nothing; the eval surface IS a subset today"
        for entry in entries:
            assert entry.get("reason", "").strip(), f"exception {entry!r} carries no reason"

    def test_it_covers_todays_known_subset(self) -> None:
        """Pins the gap the eval deliberately carries, so widening it is a diff."""
        exceptions = load_exceptions()
        assert [entry["name"] for entry in exceptions["missing_tools"]] == ["semantic_model"]
        assert sorted((entry["tool"], entry["parameter"]) for entry in exceptions["missing_parameters"]) == [
            ("run_semantic_query", "limit"),
            ("run_semantic_query", "order_by"),
        ]


class TestCli:
    def test_it_exits_non_zero_on_an_undeclared_difference(self, tmp_path: Path, capsys: Any) -> None:
        contract_path = tmp_path / "contract.json"
        surface_path = tmp_path / "surface.json"
        exceptions_path = tmp_path / "exceptions.json"
        contract_path.write_text(json.dumps(_contract(_tool("run", {}), _tool("gone", {}))), encoding="utf-8")
        surface_path.write_text(json.dumps(_surface(_surface_tool("run", {}))), encoding="utf-8")
        exceptions_path.write_text(json.dumps(_exceptions()), encoding="utf-8")

        code = contract_check._main(
            [
                "--contract",
                str(contract_path),
                "--surface",
                str(surface_path),
                "--exceptions",
                str(exceptions_path),
            ]
        )
        assert code == 1
        assert "missing-tool" in capsys.readouterr().err

    def test_it_exits_two_on_a_bad_input(self, tmp_path: Path) -> None:
        """A usage/input failure is distinguishable from a real difference."""
        surface_path = tmp_path / "surface.json"
        surface_path.write_text(json.dumps(_surface()), encoding="utf-8")
        code = contract_check._main(
            ["--contract", str(tmp_path / "absent.json"), "--surface", str(surface_path)]
        )
        assert code == 2

    def test_it_exits_zero_when_conformant(self, tmp_path: Path, capsys: Any) -> None:
        contract_path = tmp_path / "contract.json"
        surface_path = tmp_path / "surface.json"
        exceptions_path = tmp_path / "exceptions.json"
        contract_path.write_text(json.dumps(_contract(_tool("run", {}))), encoding="utf-8")
        surface_path.write_text(json.dumps(_surface(_surface_tool("run", {}))), encoding="utf-8")
        exceptions_path.write_text(json.dumps(_exceptions()), encoding="utf-8")

        code = contract_check._main(
            [
                "--contract",
                str(contract_path),
                "--surface",
                str(surface_path),
                "--exceptions",
                str(exceptions_path),
            ]
        )
        assert code == 0
        assert "semantic-contract: OK" in capsys.readouterr().out

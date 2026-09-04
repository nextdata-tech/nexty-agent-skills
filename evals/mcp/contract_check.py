"""Compare the eval MCP surface against NXD's shipped semantic MCP contract.

Ownership, stated once
----------------------
NXD owns the production contract. It builds the semantic MCP tools, derives the
served surface from its own RPC MCP registry, and publishes the result inside
the ``nxd-data_product`` wheel as ``mcp_contract.json``. This repository owns
only the eval side, and only reads. Nothing here triggers, waits on, or builds
anything in NXD — a job that needs a contract consumes an artifact NXD has
already finished publishing, or it fails.

What this module decides
------------------------
Given the production contract and the eval harness's own MCP surface, it reports
every difference that is not declared in a committed exceptions file. The eval
server is a deliberate subset today (three tools where production has four), and
that is fine as long as it is *written down*: an undeclared difference is drift,
and drift is what silently invalidates an eval.

The rules, in the direction each one catches something:

* a production tool absent from the eval surface — the eval cannot exercise it,
  so a regression in it is invisible to every scenario;
* a production parameter absent from an eval tool — a scenario that would have
  used it silently cannot;
* an eval tool or parameter production does not have — the eval is grading
  against a surface no agent will ever meet;
* a parameter whose required-ness differs — the eval accepts calls production
  rejects, or refuses calls production accepts;
* a parameter's value shape differs — the eval accepts a string where production
  expects a list, or changes the structure of a nested filter object;
* a declared exception that no longer applies — the two sides converged and
  nobody removed the note, so the file stops describing reality.

Descriptions are deliberately NOT compared. The eval server paraphrases them for
its own scenarios, and forcing them equal would make every wording change in NXD
a red build here for no behavioural reason. Descriptions ARE pinned — on the
producer's side, where the strings live: NXD's own contract test asserts the
shipped ``description_segments`` against the descriptions its factory and its
extracted entrypoints actually register. Adding a second, weaker copy of that
check here would only tell us what NXD's CI already refuses to merge.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from typing import Iterable
from typing import Sequence

CONTRACT_SCHEMA = "nxd-semantic-mcp-contract-v1"
SURFACE_SCHEMA = "nxd-eval-mcp-surface-v1"
EXCEPTIONS_SCHEMA = "nxd-semantic-mcp-exceptions-v1"

EXCEPTIONS_PATH = Path(__file__).resolve().parent / "contract_exceptions.json"


class ContractCheckError(RuntimeError):
    """An input document is missing, unreadable, or not the expected schema."""


@dataclass(frozen=True)
class Finding:
    """One undeclared difference between the two surfaces."""

    kind: str
    tool: str
    parameter: str | None
    detail: str

    def render(self) -> str:
        where = f"{self.tool}.{self.parameter}" if self.parameter else self.tool
        return f"[{self.kind}] {where}: {self.detail}"


def _read_json(path: Path, *, label: str) -> dict[str, Any]:
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ContractCheckError(f"{label} is unreadable at {path}") from exc
    try:
        document = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ContractCheckError(f"{label} at {path} is not valid JSON") from exc
    if not isinstance(document, dict):
        raise ContractCheckError(f"{label} at {path} must be a JSON object")
    return document


def _require_schema(document: dict[str, Any], expected: str, *, label: str) -> dict[str, Any]:
    if document.get("schema") != expected:
        raise ContractCheckError(f"{label} is not a {expected} document (schema={document.get('schema')!r})")
    return document


def load_contract_document(path: Path) -> dict[str, Any]:
    """Read a production contract from an explicit path."""
    return _require_schema(_read_json(path, label="the production MCP contract"), CONTRACT_SCHEMA, label="it")


def load_installed_contract() -> dict[str, Any]:
    """Read the contract out of the INSTALLED ``nxd-data_product`` distribution.

    Deliberately imports the shipped module rather than reading a path this
    repository chose: the contract that matters is the one inside the wheel the
    job installed, and a path would let a stale checkout stand in for it.
    """
    try:
        from nxd.experimental.semantic.mcp_contract import load_contract
    except ImportError as exc:  # pragma: no cover - covered by the CI job failing closed
        raise ContractCheckError(
            "nxd.experimental.semantic.mcp_contract is not importable; the NXD "
            "artifact was not installed, or it predates the shipped MCP contract"
        ) from exc
    document = load_contract()
    return _require_schema(document, CONTRACT_SCHEMA, label="the installed NXD MCP contract")


def load_surface_document(path: Path) -> dict[str, Any]:
    return _require_schema(_read_json(path, label="the eval MCP surface"), SURFACE_SCHEMA, label="it")


def load_exceptions(path: Path = EXCEPTIONS_PATH) -> dict[str, Any]:
    return _require_schema(_read_json(path, label="the contract exceptions file"), EXCEPTIONS_SCHEMA, label="it")


def _by_name(tools: Iterable[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {tool["name"]: tool for tool in tools}


def _parameters(tool: dict[str, Any]) -> dict[str, bool]:
    """Map parameter name to required-ness for one tool descriptor."""
    return {parameter["name"]: bool(parameter.get("required", False)) for parameter in tool.get("parameters", [])}


_SCHEMA_ANNOTATIONS = {"title", "description", "default", "examples", "deprecated"}


def _schema_shape(schema: Any, root: dict[str, Any], *, ignore_nullability: bool = False) -> Any:
    """Return the structural part of a JSON Schema, resolving local definitions.

    FastMCP/Pydantic adds titles, descriptions, and defaults that are not useful
    for comparing this stand-in's argument shape. Types, arrays, nested objects,
    enums, bounds, and required fields remain significant. Resolving ``$ref``
    keeps a named production model comparable to an inline consumer schema.
    ``ignore_nullability`` is used only for a parameter that already has an
    explicit required-ness exception: NXD's generated schema expresses that
    known difference as both ``optional`` and ``nullable``.
    """
    if not isinstance(schema, dict):
        return schema
    reference = schema.get("$ref")
    if isinstance(reference, str) and reference.startswith("#/$defs/"):
        definition = root.get("$defs", {}).get(reference.removeprefix("#/$defs/"))
        if isinstance(definition, dict):
            return _schema_shape(definition, root, ignore_nullability=ignore_nullability)

    shape: dict[str, Any] = {}
    for key, value in schema.items():
        if key in _SCHEMA_ANNOTATIONS or key == "$defs":
            continue
        if key == "properties" and isinstance(value, dict):
            shape[key] = {name: _schema_shape(child, root) for name, child in sorted(value.items())}
        elif key in {"anyOf", "oneOf", "allOf"} and isinstance(value, list):
            choices = [
                _schema_shape(choice, root, ignore_nullability=ignore_nullability)
                for choice in value
                if not (ignore_nullability and choice == {"type": "null"})
            ]
            if len(choices) == 1:
                return choices[0]
            shape[key] = sorted(choices, key=lambda choice: json.dumps(choice, sort_keys=True))
        elif key == "required" and isinstance(value, list):
            shape[key] = sorted(value)
        elif isinstance(value, dict):
            shape[key] = _schema_shape(value, root, ignore_nullability=ignore_nullability)
        else:
            shape[key] = value
    return shape


def _parameter_schema(tool: dict[str, Any], parameter: str, *, ignore_nullability: bool = False) -> Any:
    schema = tool.get("input_schema")
    if not isinstance(schema, dict):
        return None
    properties = schema.get("properties")
    if not isinstance(properties, dict) or parameter not in properties:
        return None
    return _schema_shape(properties[parameter], schema, ignore_nullability=ignore_nullability)


def _declared_tools(exceptions: dict[str, Any], key: str) -> dict[str, str]:
    return {entry["name"]: entry["reason"] for entry in exceptions.get(key, [])}


def _declared_parameters(exceptions: dict[str, Any], key: str) -> dict[tuple[str, str], str]:
    return {(entry["tool"], entry["parameter"]): entry["reason"] for entry in exceptions.get(key, [])}


def check(
    contract: dict[str, Any],
    surface: dict[str, Any],
    exceptions: dict[str, Any],
) -> list[Finding]:
    """Return every undeclared difference. An empty list means conformant."""
    production = _by_name(contract["tools"])
    evaluated = _by_name(surface["tools"])

    missing_tools = _declared_tools(exceptions, "missing_tools")
    extra_tools = _declared_tools(exceptions, "extra_tools")
    missing_parameters = _declared_parameters(exceptions, "missing_parameters")
    extra_parameters = _declared_parameters(exceptions, "extra_parameters")
    parameter_mismatches = _declared_parameters(exceptions, "parameter_mismatches")
    parameter_schema_mismatches = _declared_parameters(exceptions, "parameter_schema_mismatches")

    findings: list[Finding] = []

    for name in sorted(set(production) - set(evaluated)):
        if name in missing_tools:
            continue
        findings.append(
            Finding(
                "missing-tool",
                name,
                None,
                "production serves this tool and the eval surface does not; declare it in "
                f"{EXCEPTIONS_PATH.name} with a reason, or add it to the eval server",
            )
        )

    for name in sorted(set(evaluated) - set(production)):
        if name in extra_tools:
            continue
        findings.append(
            Finding(
                "unexplained-tool",
                name,
                None,
                "the eval surface serves a tool production does not; scenarios grading it "
                "are grading a surface no agent will meet",
            )
        )

    for name in sorted(set(production) & set(evaluated)):
        produced = _parameters(production[name])
        evaluated_parameters = _parameters(evaluated[name])

        for parameter in sorted(set(produced) - set(evaluated_parameters)):
            if (name, parameter) in missing_parameters:
                continue
            findings.append(
                Finding(
                    "missing-parameter",
                    name,
                    parameter,
                    "production accepts this argument and the eval tool does not",
                )
            )

        for parameter in sorted(set(evaluated_parameters) - set(produced)):
            if (name, parameter) in extra_parameters:
                continue
            findings.append(
                Finding(
                    "unexplained-parameter",
                    name,
                    parameter,
                    "the eval tool accepts an argument production does not",
                )
            )

        for parameter in sorted(set(produced) & set(evaluated_parameters)):
            ignore_nullability = (name, parameter) in parameter_mismatches
            if _parameter_schema(
                production[name], parameter, ignore_nullability=ignore_nullability
            ) != _parameter_schema(evaluated[name], parameter, ignore_nullability=ignore_nullability):
                if (name, parameter) not in parameter_schema_mismatches:
                    findings.append(
                        Finding(
                            "parameter-schema",
                            name,
                            parameter,
                            "production and the eval surface describe different value shapes",
                        )
                    )
            if produced[parameter] == evaluated_parameters[parameter]:
                continue
            if (name, parameter) in parameter_mismatches:
                continue
            expected = "required" if produced[parameter] else "optional"
            actual = "required" if evaluated_parameters[parameter] else "optional"
            findings.append(
                Finding(
                    "parameter-requiredness",
                    name,
                    parameter,
                    f"production treats it as {expected}, the eval surface as {actual}",
                )
            )

    findings.extend(_stale_exceptions(production, evaluated, exceptions))
    return findings


def _stale_exceptions(
    production: dict[str, dict[str, Any]],
    evaluated: dict[str, dict[str, Any]],
    exceptions: dict[str, Any],
) -> list[Finding]:
    """Flag declared exceptions that no longer describe a real difference.

    Without this, the file rots into a permanent waiver: the day the eval server
    grows the missing tool, the exception keeps sitting there and the next real
    divergence gets waived by a note written about something else.
    """
    findings: list[Finding] = []

    for name in sorted(_declared_tools(exceptions, "missing_tools")):
        if name not in production:
            findings.append(
                Finding("stale-exception", name, None, "declared as a missing tool, but production does not serve it")
            )
        elif name in evaluated:
            findings.append(
                Finding("stale-exception", name, None, "declared as a missing tool, but the eval surface now has it")
            )

    for name in sorted(_declared_tools(exceptions, "extra_tools")):
        if name not in evaluated:
            findings.append(
                Finding("stale-exception", name, None, "declared as an extra tool, but the eval surface lacks it")
            )
        elif name in production:
            findings.append(
                Finding("stale-exception", name, None, "declared as an extra tool, but production now serves it")
            )

    for tool, parameter in sorted(_declared_parameters(exceptions, "missing_parameters")):
        produced = _parameters(production[tool]) if tool in production else {}
        evaluated_parameters = _parameters(evaluated[tool]) if tool in evaluated else {}
        if parameter not in produced:
            findings.append(
                Finding(
                    "stale-exception",
                    tool,
                    parameter,
                    "declared as a missing parameter, but production does not accept it",
                )
            )
        elif parameter in evaluated_parameters:
            findings.append(
                Finding(
                    "stale-exception",
                    tool,
                    parameter,
                    "declared as a missing parameter, but the eval tool now accepts it",
                )
            )

    for tool, parameter in sorted(_declared_parameters(exceptions, "extra_parameters")):
        evaluated_parameters = _parameters(evaluated[tool]) if tool in evaluated else {}
        produced = _parameters(production[tool]) if tool in production else {}
        if parameter not in evaluated_parameters:
            findings.append(
                Finding(
                    "stale-exception",
                    tool,
                    parameter,
                    "declared as an extra parameter, but the eval tool does not accept it",
                )
            )
        elif parameter in produced:
            findings.append(
                Finding(
                    "stale-exception", tool, parameter, "declared as an extra parameter, but production now accepts it"
                )
            )

    for tool, parameter in sorted(_declared_parameters(exceptions, "parameter_mismatches")):
        produced = _parameters(production[tool]) if tool in production else {}
        evaluated_parameters = _parameters(evaluated[tool]) if tool in evaluated else {}
        if parameter not in produced or parameter not in evaluated_parameters:
            findings.append(
                Finding(
                    "stale-exception",
                    tool,
                    parameter,
                    "declared as a required-ness mismatch, but the parameter is absent from one side",
                )
            )
        elif produced[parameter] == evaluated_parameters[parameter]:
                findings.append(
                    Finding("stale-exception", tool, parameter, "declared as a required-ness mismatch, but they now agree")
                )

    for tool, parameter in sorted(_declared_parameters(exceptions, "parameter_schema_mismatches")):
        produced = _parameters(production[tool]) if tool in production else {}
        evaluated_parameters = _parameters(evaluated[tool]) if tool in evaluated else {}
        if parameter not in produced or parameter not in evaluated_parameters:
            findings.append(
                Finding(
                    "stale-exception",
                    tool,
                    parameter,
                    "declared as a schema mismatch, but the parameter is absent from one side",
                )
            )
        elif _parameter_schema(production[tool], parameter) == _parameter_schema(evaluated[tool], parameter):
            findings.append(
                Finding("stale-exception", tool, parameter, "declared as a schema mismatch, but they now agree")
            )

    return findings


def _main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="contract_check")
    parser.add_argument(
        "--surface",
        required=True,
        type=Path,
        help=f"path to a {SURFACE_SCHEMA} document (see contract_surface.py)",
    )
    parser.add_argument(
        "--contract",
        type=Path,
        default=None,
        help="path to a production contract; defaults to the installed nxd-data_product's",
    )
    parser.add_argument("--exceptions", type=Path, default=EXCEPTIONS_PATH)
    args = parser.parse_args(argv)

    try:
        contract = load_contract_document(args.contract) if args.contract else load_installed_contract()
        surface = load_surface_document(args.surface)
        exceptions = load_exceptions(args.exceptions)
    except ContractCheckError as exc:
        print(f"semantic-contract: FAIL (input): {exc}", file=sys.stderr)
        return 2

    findings = check(contract, surface, exceptions)
    if findings:
        print(f"semantic-contract: FAIL — {len(findings)} undeclared difference(s)", file=sys.stderr)
        for finding in findings:
            print(f"  {finding.render()}", file=sys.stderr)
        return 1

    declared = sum(
        len(exceptions.get(key, []))
        for key in (
            "missing_tools",
            "extra_tools",
            "missing_parameters",
            "extra_parameters",
            "parameter_mismatches",
            "parameter_schema_mismatches",
        )
    )
    print(
        f"semantic-contract: OK — {len(contract['tools'])} production tool(s), "
        f"{len(surface['tools'])} eval tool(s), {declared} declared exception(s)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())

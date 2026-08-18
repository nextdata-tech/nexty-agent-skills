#!/usr/bin/env python3
"""Fail-closed checker for the terminal mapper-adapter scenario."""
from __future__ import annotations

import argparse
import ast
import json
import os
from pathlib import Path


PUBLIC_MAPPER_MODULE = "nxd.experimental.field_mapper"


def _attribute_name(node: ast.AST) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        parent = _attribute_name(node.value)
        return f"{parent}.{node.attr}" if parent else node.attr
    return None


def findings(source: str) -> list[str]:
    tree = ast.parse(source)
    imported: set[str] = set()
    module_aliases: set[str] = set()
    adapter_names: set[str] = set()
    map_names: set[str] = set()
    map_calls: list[ast.Call] = []
    make_call_calls: list[ast.Call] = []
    raw_return = False
    proposal_attribute_access = False

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imported.add(alias.name)
                if alias.name == PUBLIC_MAPPER_MODULE:
                    module_aliases.add(alias.asname or alias.name)
                elif alias.name == "nxd.experimental":
                    module_aliases.add(f"{alias.asname or alias.name}.field_mapper")
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            imported.add(module)
            imported.update(f"{module}.{alias.name}" for alias in node.names if module)
            if module == PUBLIC_MAPPER_MODULE:
                for alias in node.names:
                    local = alias.asname or alias.name
                    if alias.name == "make_call":
                        adapter_names.add(local)
                    elif alias.name == "map_inputs":
                        map_names.add(local)
            elif module == "nxd.experimental":
                for alias in node.names:
                    if alias.name == "field_mapper":
                        module_aliases.add(alias.asname or alias.name)
        elif isinstance(node, ast.Call):
            dotted = _attribute_name(node.func)
            if dotted in {"importlib.import_module", "import_module"}:
                if not node.args or not isinstance(node.args[0], ast.Constant) or not isinstance(node.args[0].value, str):
                    imported.add("<dynamic import>")
                elif node.args[0].value == "anthropic" or node.args[0].value.startswith("anthropic."):
                    imported.add(node.args[0].value)
            if dotted == "__import__":
                if not node.args or not isinstance(node.args[0], ast.Constant) or not isinstance(node.args[0].value, str):
                    imported.add("<dynamic import>")
                elif node.args[0].value == "anthropic" or node.args[0].value.startswith("anthropic."):
                    imported.add(node.args[0].value)
            if dotted == "getattr" and node.args:
                target = _attribute_name(node.args[0])
                if target and target.split(".", 1)[0] == "proposal":
                    proposal_attribute_access = True
            if dotted == "getattr" and len(node.args) > 1:
                attribute = node.args[1]
                if isinstance(attribute, ast.Constant) and attribute.value in {"transport", "ledger"}:
                    imported.add(f"field_mapper.{attribute.value}")
                elif not isinstance(attribute, ast.Constant):
                    imported.add("field_mapper.<dynamic private access>")
            if (
                isinstance(node.func, ast.Name) and node.func.id in map_names
            ) or dotted in {f"{alias}.map_inputs" for alias in module_aliases}:
                map_calls.append(node)
            if (
                isinstance(node.func, ast.Name) and node.func.id in adapter_names
            ) or dotted in {f"{alias}.make_call" for alias in module_aliases}:
                make_call_calls.append(node)
        elif isinstance(node, ast.Attribute):
            target = _attribute_name(node.value)
            if target and target.split(".", 1)[0] == "proposal":
                proposal_attribute_access = True
        elif isinstance(node, ast.Return):
            value = node.value
            if isinstance(value, ast.Name):
                raw_return = raw_return or value.id.lower() in {
                    "message", "response", "resp", "raw_response", "sdk_response"
                }
            elif isinstance(value, ast.Attribute):
                raw_return = raw_return or value.attr.lower() in {
                    "message", "response", "resp", "raw_response", "sdk_response"
                }

    errors: list[str] = []
    if any(name == "anthropic" or name.startswith("anthropic.") or name == "<dynamic import>" for name in imported):
        errors.append("provider SDK import")
    if any(
        "field_mapper.transport" in name
        or "field_mapper.ledger" in name
        or "field_mapper.<dynamic private access>" in name
        for name in imported
    ):
        errors.append("private mapper import")
    if proposal_attribute_access:
        errors.append("undocumented proposal attribute")
    if raw_return:
        errors.append("raw provider response return")
    if not make_call_calls:
        errors.append("public make_call call missing")
    if not map_calls:
        errors.append("map_inputs call missing")
    elif not any(any(keyword.arg == "call" for keyword in call.keywords) for call in map_calls):
        errors.append("map_inputs must receive call=")
    return errors


def artifact_contains_secret(root: Path, markers: tuple[str, ...]) -> bool | str:
    """Scan landed artifacts in bounded chunks without following symlinks."""
    needles = tuple(marker.lower().encode("utf-8") for marker in markers)
    if not needles:
        return False
    overlap = max(len(needle) for needle in needles) - 1
    for directory, dirnames, filenames in os.walk(root, followlinks=False):
        dirnames[:] = [
            name for name in dirnames if not (Path(directory) / name).is_symlink()
        ]
        for filename in filenames:
            path = Path(directory) / filename
            if path.is_symlink() or not path.is_file():
                continue
            try:
                with path.open("rb") as handle:
                    carry = b""
                    while chunk := handle.read(64 * 1024):
                        data = (carry + chunk).lower()
                        if any(needle in data for needle in needles):
                            return True
                        carry = data[-overlap:] if overlap else b""
            except OSError:
                # An unreadable artifact cannot be cleared as secret-free.
                return "unreadable"
    return False


def trace_errors(trace_text: str) -> list[str]:
    """Require runner-authored JSON-RPC events, never agent prose."""
    events: list[dict[str, object]] = []
    for line in trace_text.splitlines():
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            return ["trace is not runner-authored JSON-RPC"]
        if not isinstance(event, dict) or event.get("source") != "runner" or event.get("protocol") != "mcp":
            return ["trace is not runner-authored JSON-RPC"]
        events.append(event)
    if not events:
        return ["missing runner-authored MCP trace event"]
    if not any(event.get("method") == "tools/call" for event in events):
        return ["trace has no nxd-desktop MCP tool call"]
    if not any(
        event.get("method") == "tools/call"
        and event.get("tool") in {"build_data_product", "inspect_run"}
        for event in events
    ):
        return ["trace has no mapper build/inspection event"]
    return []


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--fixtures", required=True)
    ap.add_argument("--root", required=True)
    ap.add_argument("--trace", required=True)
    ap.add_argument("--secret-marker-file")
    args = ap.parse_args()
    root, trace, fixtures = Path(args.root), Path(args.trace), Path(args.fixtures)
    errors: list[str] = []
    if not fixtures.is_dir():
        errors.append("fixtures directory missing")
    source_path = root / "transform" / "main.py"
    if not source_path.is_file():
        errors.append("missing transform/main.py")
    else:
        errors.extend(findings(source_path.read_text(encoding="utf-8")))

    markers: tuple[str, ...] = ()
    marker_read_failed = False
    if args.secret_marker_file:
        marker_path = Path(args.secret_marker_file)
        try:
            markers = tuple(line for line in marker_path.read_text(encoding="utf-8").splitlines() if line)
        except OSError:
            marker_read_failed = True
            errors.append("secret marker file unreadable")
    if not markers and not marker_read_failed:
        errors.append("redaction markers are required")
    else:
        artifact_result = artifact_contains_secret(root, markers)
        if artifact_result == "unreadable":
            errors.append("artifact unreadable, cannot clear")
        elif artifact_result:
            errors.append("credential material appears in artifact")

    if not trace.is_file():
        errors.append("missing public MCP trace")
    else:
        trace_bytes = trace.read_bytes()
        trace_text = trace_bytes.decode("utf-8", errors="ignore")
        errors.extend(trace_errors(trace_text))
        lowered_trace = trace_bytes.lower()
        if markers and any(marker.lower().encode("utf-8") in lowered_trace for marker in markers):
            errors.append("credential material appears in trace")
    if errors:
        for error in errors:
            print(f"FAIL {error}")
        return 1
    print("ALL CHECKS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

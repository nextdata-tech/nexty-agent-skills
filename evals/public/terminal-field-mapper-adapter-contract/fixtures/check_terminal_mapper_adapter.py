#!/usr/bin/env python3
"""Fail-closed checker for the terminal mapper-adapter scenario."""
from __future__ import annotations

import argparse
import ast
from pathlib import Path

def findings(source: str) -> list[str]:
    tree = ast.parse(source)
    imported: set[str] = set()
    adapter_names: set[str] = set()
    map_calls: list[ast.Call] = []
    raw_return = False
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            imported.add(module)
            imported.update(f"{module}.{alias.name}" for alias in node.names if module)
            if module == "nxd.experimental.field_mapper":
                adapter_names.update(alias.asname or alias.name for alias in node.names if alias.name == "make_call")
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "map_inputs":
            map_calls.append(node)
        elif isinstance(node, ast.Return) and isinstance(node.value, ast.Name) and node.value.id.lower() in {"message", "response"}:
            raw_return = True
    errors: list[str] = []
    if any(name == "anthropic" or name.startswith("anthropic.") for name in imported):
        errors.append("provider SDK import")
    if any("field_mapper.transport" in name or "field_mapper.ledger" in name for name in imported):
        errors.append("private mapper import")
    if raw_return:
        errors.append("raw provider response return")
    if not adapter_names:
        errors.append("public make_call import missing")
    if not map_calls:
        errors.append("map_inputs call missing")
    elif not any(any(k.arg == "call" for k in call.keywords) for call in map_calls):
        errors.append("map_inputs must receive call=")
    return errors


def artifact_contains_secret(root: Path, markers: tuple[str, ...]) -> bool:
    """Scan landed text artifacts without echoing the matching content."""
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8", errors="ignore").lower()
        if any(marker.lower() in text for marker in markers):
            return True
    return False


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--fixtures", required=True)
    ap.add_argument("--root", required=True)
    ap.add_argument("--trace", required=True)
    ap.add_argument("--secret-marker", action="append", default=[])
    args = ap.parse_args()
    root, trace = Path(args.root), Path(args.trace)
    source_path = root / "transform" / "main.py"
    errors: list[str] = []
    if not source_path.is_file():
        errors.append("missing transform/main.py")
    else:
        errors.extend(findings(source_path.read_text(encoding="utf-8")))
    markers = tuple(str(marker) for marker in args.secret_marker if marker)
    if artifact_contains_secret(root, markers):
        errors.append("credential material appears in artifact")
    if not trace.is_file():
        errors.append("missing public MCP trace")
    else:
        trace_text = trace.read_text(encoding="utf-8", errors="ignore")
        if "nxd-desktop" not in trace_text:
            errors.append("trace has no nxd-desktop MCP event")
        if not ("build_data_product" in trace_text or "inspect_run" in trace_text):
            errors.append("trace has no mapper build/inspection event")
        if any(marker.lower() in trace_text.lower() for marker in markers):
            errors.append("credential material appears in trace")
    if errors:
        for error in errors:
            print(f"FAIL {error}")
        return 1
    print("ALL CHECKS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

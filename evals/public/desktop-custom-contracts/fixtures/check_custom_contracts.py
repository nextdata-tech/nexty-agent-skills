#!/usr/bin/env python3
"""Fail-closed structural checker for the public desktop custom-contract eval."""
from __future__ import annotations
import argparse
import ast
import re
from pathlib import Path

# Byte-identical to scripts/self_check.py's SECRET_LITERAL. Restating it drifted
# in BOTH directions: `passwd` was missing here (Phase C failed, this passed)
# and the missing \b made `csrf_token` match here but not there (this failed,
# Phase C passed). Either way a closure passes one gate and fails the other,
# which is worse than either gate alone.
# Three arms, each bounded at an identifier boundary.
#   1. the credential word as a SUFFIX, with any prefix — `db_password`,
#      `openai_api_key`, `MY_SECRET`. A uniform leading \b missed all three.
#   2. the credential word as a PREFIX of `_key` — `SECRET_KEY`, `private_key`,
#      `aws_secret_access_key`. Arm 1 only sees suffixes, so these escaped it,
#      and `SECRET_KEY = "..."` is about as idiomatic as a Python secret gets.
#      Deliberately NOT bare `*_key`: `sort_key`, `primary_key` and `cache_key`
#      are not credentials.
#   3. `token`, narrowest of the three: bare, or behind a prefix that denotes a
#      credential. Each prefix is bounded — unbounded, `id` let `valid_token`,
#      `uuid_token` and `grid_token` in. The bare arm excludes `-` as well as
#      word characters, because \b treats a hyphen as a boundary and
#      `csrf-token` would otherwise escape the carve-out `csrf_token` gets.
# Non-assignments (`password_columns`, `token_fields`, `tokenizer`) match none.
SECRET_LITERAL = re.compile(
    r"(?i)(?:(?:^|[^A-Za-z0-9])[A-Za-z0-9_]*(?:api[_-]?key|password|passwd|secret)"
    r"|(?:^|[^A-Za-z0-9])(?:secret|private|signing|encryption"
    r"|aws[_-]?secret[_-]?access)[_-]key"
    r"|(?:^|[^A-Za-z0-9])(?:access|auth|oauth|refresh|bearer|session|api|jwt|id"
    r"|secret|private|github|gitlab|slack)[_-]token"
    r"|(?:^|[^A-Za-z0-9_-])token)\s*=\s*[\"']")


def calls(node):
    out = []
    while isinstance(node, ast.Call):
        out.append(node)
        node = node.func.value if isinstance(node.func, ast.Attribute) else None
    return out

def name(node):
    return node.func.attr if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) else (node.func.id if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) else "")

def is_contract_path(value):
    path = Path(value)
    return value.startswith("contracts/") and path.suffix == ".py" and not path.is_absolute() and ".." not in path.parts

def has_main_guard(tree):
    for node in tree.body:
        if not (isinstance(node, ast.If) and isinstance(node.test, ast.Compare)
                and isinstance(node.test.left, ast.Name) and node.test.left.id == "__name__"
                and len(node.test.ops) == len(node.test.comparators) == 1
                and isinstance(node.test.ops[0], ast.Eq)
                and isinstance(node.test.comparators[0], ast.Constant)
                and node.test.comparators[0].value == "__main__"):
            continue
        if any(isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Call)
               and isinstance(stmt.value.func, ast.Attribute)
               and stmt.value.func.attr == "verify"
               and isinstance(stmt.value.func.value, ast.Name)
               and stmt.value.func.value.id == "data_product"
               for stmt in node.body):
            return True
    return False

def has_service_driver(profile_text, service, driver):
    block = re.search(rf"(?ms)^\s*-\s*name:\s*{re.escape(service)}\s*$((?:(?!^\s*-\s*name:).)*)", profile_text)
    return bool(block and re.search(rf"^\s*driver:\s*{re.escape(driver)}\s*$", block.group(1), re.MULTILINE))

def check(root: Path):
    errors = []
    # Codex stages skill context under hidden workspace directories such as
    # `.skills/`. Those files are inputs to the agent, not generated closure
    # artifacts, and must not make an otherwise singular authored spec look
    # ambiguous.
    specs = [
        path for path in root.rglob("spec.py")
        if not any(part.startswith(".") for part in path.relative_to(root).parts)
    ]
    if len(specs) != 1: return ["expected exactly one generated spec.py"]
    text = specs[0].read_text(); tree = ast.parse(text)
    bindings = {
        target.id: value.value
        for node in tree.body if isinstance(node, ast.Assign)
        for target in node.targets if isinstance(target, ast.Name)
        for value in [node.value]
        if isinstance(value, ast.Constant) and isinstance(value.value, str)
    }
    # Builders hoisted into a variable — `_in = source_aligned_input()...` then
    # `.input("orders", _in)` — must be inspected too. Without this the whole
    # CSV-input gate silently skips (`expectations` comes back empty and the
    # loop `continue`s), so a closure with an absolute model path and a
    # non-csv-source binding prints ALL CHECKS PASSED while self_check.py, which
    # walks the whole tree, rejects it.
    builders = {
        target.id: node.value
        for node in tree.body if isinstance(node, ast.Assign)
        for target in node.targets if isinstance(target, ast.Name)
        if isinstance(node.value, ast.Call)
    }

    def resolve(node):
        """A call expression, following one level of single-assignment hoisting."""
        if isinstance(node, ast.Name):
            return builders.get(node.id, node)
        return node

    profile = specs[0].parent / "infra-profile.yaml"
    profile_text = profile.read_text() if profile.is_file() else ""
    required_services = {
        "duckdb": "nxd:local/duckdb/storage:0.1.0",
        "python-compute": "nxd:local/python/compute:0.1.0",
        "csv-source": "nxd:local/file/storage:0.1.0",
    }
    if ("name: desktop-local" not in profile_text or any(
            not has_service_driver(profile_text, service, driver)
            for service, driver in required_services.items())):
        errors.append("infra-profile.yaml lacks the desktop-local DuckDB, compute, and csv-source services")
    source_path_file = specs[0].parent / "csv-source-path"
    source_root_text = source_path_file.read_text().strip() if source_path_file.is_file() else ""
    source_root_parts = source_root_text.replace("\\", "/").split("/") if source_root_text else []
    source_root = specs[0].parent / source_root_text if source_root_text else None
    if (not source_root_text or Path(source_root_text).is_absolute() or
            any(part in ("", ".", "..") for part in source_root_parts) or
            not source_root or not source_root.is_dir()):
        errors.append("csv-source-path must name an existing contained relative export root")
    names, scripts, contract_scripts, contracts, input_n, output_n = [], set(), [], 0, 0, 0
    for n in ast.walk(tree):
        if not isinstance(n, ast.Call): continue
        if name(n) == "custom" and n.args and isinstance(n.args[0], ast.Constant): names.append(n.args[0].value)
        if name(n) in ("expectation", "promise") and n.args:
            chain = calls(n.args[0])
            if any(name(c) == "custom" for c in chain):
                contracts += 1
                input_n += name(n) == "expectation"; output_n += name(n) == "promise"
                if not any(name(c) == "description" and c.args and isinstance(c.args[0], ast.Constant) and c.args[0].value for c in chain): errors.append("custom description missing")
                if not any(name(c) == "model" and c.args and isinstance(c.args[0], ast.Name) for c in chain): errors.append("custom model missing")
                verifies = [c for c in chain if name(c) == "verify"]
                if len(verifies) != 1:
                    errors.append("custom contract must have exactly one verify(script(...).compute(_compute))")
                    continue
                verify = verifies[0]
                verifier_chain = calls(verify.args[0]) if len(verify.args) == 1 and not verify.keywords else []
                script_calls = [c for c in verifier_chain if name(c) == "script"]
                valid_shape = (
                    len(verifier_chain) == 2
                    and name(verify.args[0]) == "compute"
                    and len(verify.args[0].args) == 1
                    and not verify.args[0].keywords
                    and isinstance(verify.args[0].args[0], ast.Name)
                    and verify.args[0].args[0].id == "_compute"
                    and len(script_calls) == 1
                    and len(script_calls[0].args) == 1
                    and not script_calls[0].keywords
                    and isinstance(script_calls[0].args[0], ast.Constant)
                    and isinstance(script_calls[0].args[0].value, str)
                )
                if not valid_shape:
                    errors.append("custom verifier must use script(...).compute(_compute)")
                    continue
                rel = script_calls[0].args[0].value
                if not is_contract_path(rel):
                    errors.append(f"custom verifier path must be a relative contracts/*.py file: {rel}")
                else:
                    scripts.add(rel)
                    contract_scripts.append(rel)
    if len(names) != len(set(names)) or len(names) < 2: errors.append("distinct custom names missing")
    if contracts != len(names): errors.append("each custom contract must be attached to an expectation or promise")
    if len(contract_scripts) != len(set(contract_scripts)):
        errors.append("custom contracts must use unique verifier scripts")
    if not input_n or not output_n: errors.append("input expectation/output schema+custom promise placement missing")
    for n in ast.walk(tree):
        if name(n) != "input" or len(n.args) < 2:
            continue
        chain = calls(resolve(n.args[1]))
        expectations = [c for c in chain if name(c) == "expectation" and c.args
                        and any(name(part) == "custom" for part in calls(c.args[0]))]
        if not expectations:
            continue
        custom_models = [part.args[0].id for expectation in expectations
                         for part in calls(expectation.args[0])
                         if name(part) == "model" and part.args and isinstance(part.args[0], ast.Name)]
        configs = [c for c in chain if name(c) == "config" and c.args and isinstance(c.args[0], ast.Dict)]
        mappings, found_mapping = {}, False
        for config in configs:
            for key, value in zip(config.args[0].keys, config.args[0].values):
                if not (isinstance(key, ast.Constant) and key.value == "model_paths"):
                    continue
                found_mapping = True
                if not isinstance(value, ast.Dict) or not value.keys:
                    errors.append("CSV input model_paths must be a non-empty literal mapping")
                    continue
                for model_key, path_value in zip(value.keys, value.values):
                    model_key = model_key.value if isinstance(model_key, ast.Constant) and isinstance(model_key.value, str) else None
                    rel = path_value.value if isinstance(path_value, ast.Constant) and isinstance(path_value.value, str) else None
                    components = rel.replace("\\", "/").split("/") if rel else []
                    if (not model_key or not model_key.strip() or not rel or Path(rel).is_absolute() or
                            rel.endswith("/") or not rel.endswith(".csv") or
                            any(part in ("", ".", "..") for part in components)):
                        errors.append("CSV input model_paths must use non-empty model keys and contained relative .csv paths")
                        continue
                    mappings[model_key] = rel
        if not found_mapping:
            errors.append("CSV input model_paths must be a non-empty literal mapping")
        if not any(name(c) == "source_aligned_input" for c in chain) or not any(
                name(c) == "source" and c.args and isinstance(c.args[0], ast.Name)
                and c.args[0].id == "_csv" for c in chain) or bindings.get("_csv") != (
                    "/infra-profile/desktop-local#/services/csv-source"):
            errors.append(
                "custom input expectation must use source_aligned_input().source(_csv) "
                "bound exactly to the unlabeled desktop-local csv-source service"
            )
        for model in custom_models:
            rel = mappings.get(model)
            if not rel:
                errors.append(f"CSV input model_paths missing safe relative mapping for {model}")
            elif not source_root or not (source_root / rel).is_file():
                errors.append(f"CSV input model_paths must resolve under csv-source-path/: {rel}")
    for n in ast.walk(tree):
        if name(n) != "output" or not n.args:
            continue
        chain = calls(resolve(n.args[0]))
        custom_promises = [c for c in chain if name(c) == "promise" and c.args
                           and any(name(part) == "custom" for part in calls(c.args[0]))]
        if not custom_promises:
            continue
        custom_models = [part.args[0].id for promise in custom_promises
                         for part in calls(promise.args[0])
                         if name(part) == "model" and part.args and isinstance(part.args[0], ast.Name)]
        ordinary_models = {promise.args[0].id for promise in chain
                           if name(promise) == "promise" and promise.args
                           and isinstance(promise.args[0], ast.Name)}
        if not set(custom_models) <= ordinary_models:
            errors.append("custom output promise must retain ordinary promise(model)")
        # Check the BINDING, not just the variable name: `_duckdb` pointing at
        # the csv-source ref is exactly the swap self_check.py rejects, and a
        # name-only check would pass a closure that gate fails.
        if not any(name(port) == "port" and len(port.args) >= 2
                   and isinstance(port.args[0], ast.Constant) and port.args[0].value == "duckdb"
                   and name(port.args[1]) == "storage" and port.args[1].args
                   and isinstance(port.args[1].args[0], ast.Name)
                   and bindings.get(port.args[1].args[0].id)
                   == "/infra-profile/desktop-local#/services/duckdb"
                   for port in chain):
            errors.append("custom output promise must be on a DuckDB output port")
    for rel in scripts:
        p = specs[0].parent / rel
        if not p.is_file(): errors.append(f"missing script {rel}"); continue
        t = ast.parse(p.read_text())
        verifiers = [f for f in ast.walk(t)
                     if isinstance(f, (ast.FunctionDef, ast.AsyncFunctionDef)) and
                     any(name(d) == "on_verify" for d in f.decorator_list)]
        registered = len(verifiers)
        source = p.read_text(); verifier = next(iter(verifiers), None)
        verifier_source = ast.unparse(verifier) if verifier else ""
        # Deliberately the SAME predicate as scripts/self_check.py: a non-literal
        # If/IfExp anywhere in the function, with FAILED present in the body —
        # NOT "FAILED lexically inside the branch". The stricter form rejects the
        # inverted guard clause (`if not violations: return PASS` / bare
        # `return FAILED`), which self_check accepts, and a closure that passes
        # one gate and fails the other is worse than either gate alone.
        conditional_failed = verifier and any(
            not isinstance(branch.test, ast.Constant)
            for branch in ast.walk(verifier)
            if isinstance(branch, (ast.If, ast.IfExp)))
        # A stub body — `def verify(): pass` / `...` — is inert. Walking the
        # WHOLE function instead false-positives on `except KeyError: pass`,
        # which is ordinary error handling, and self_check.py does not reject
        # it; the gates must not disagree.
        stub_body = bool(verifier) and all(
            isinstance(n, ast.Pass)
            or (isinstance(n, ast.Expr) and isinstance(n.value, ast.Constant)
                and n.value.value is Ellipsis)
            for n in verifier.body)
        inert = not verifier or stub_body or "FAILED" not in verifier_source or "PASS" not in verifier_source or not conditional_failed
        if registered != 1 or not has_main_guard(t) or inert: errors.append(f"bad verifier {rel}")
        if any(isinstance(f, ast.AsyncFunctionDef) for f in verifiers):
            errors.append("Desktop custom verifier must be synchronous; the runtime does not await async verifier functions")
        if SECRET_LITERAL.search(source): errors.append(f"secret-like assignment in {rel}")
    for p in (specs[0].parent / "contracts").rglob("*.py") if (specs[0].parent / "contracts").exists() else []:
        if str(p.relative_to(specs[0].parent)) not in scripts: errors.append(f"decorative script {p}")
    for p in [specs[0], profile]:
        if p.is_file() and re.search(r'(?i)(api[_-]?key|password|token|secret)\s*[:=]\s*["\']', p.read_text()):
            errors.append(f"secret-like literal in {p.name}")
    return errors

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", type=Path, required=True)
    ap.add_argument("--fixtures", type=Path)
    args = ap.parse_args()
    errors = check(args.root)
    for error in errors:
        print("FAIL", error)
    if errors:
        return 1
    print("ALL CHECKS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

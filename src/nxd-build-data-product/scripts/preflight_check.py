#!/usr/bin/env python3
"""Static preflight for a generated Nextdata OS data product.

Checks the four faults that `nxd validate` structurally cannot catch, because it
imports the bundle and resolves services but never executes a transform, never
executes a contract, and never installs the package:

  flat-layout   several shipped top-level modules with no packaging guard, which
                fails at `nxd launch` with "Multiple top-level modules discovered
                in a flat-layout"
  verify-bind   a contract whose service-context parameter is not named after a
                declared service, input or port; arguments bind by name
  verify-weak   a contract that can only ever return PASS, so it asserts nothing
  version-drift `spec.py` and `pyproject.toml` disagree on the version
  contract-driver a contract wired with the contract-executor driver instead of
                the storage driver, which hands it a bare Context
  surface      an access/approval modifier or an executor config block that no
                README or checklist line justifies; these change deployed
                behaviour and are easy to add to look thorough

Standard library only, and it never imports the product under test, so it runs
before dependencies are installed and cannot be defeated by an import error.

    python3 preflight_check.py <data_product_directory>

Exits 0 when clean, 1 when any ERROR-level finding is reported. Findings are
advisory input to the Generated-Code Preflight in the skill, not a substitute for
reading the code.
"""

from __future__ import annotations

import argparse
import ast
import fnmatch
import re
import sys
from dataclasses import dataclass
from pathlib import Path

ERROR = "ERROR"
WARN = "WARN"


@dataclass(frozen=True)
class Finding:
    level: str
    check: str
    location: str
    message: str

    def render(self) -> str:
        return f"{self.level}[{self.check}] {self.location}: {self.message}"


def _nxdignore_patterns(root: Path) -> list[str]:
    path = root / ".nxdignore"
    if not path.exists():
        return []
    patterns = []
    for raw in path.read_text().splitlines():
        line = raw.strip()
        if line and not line.startswith("#"):
            patterns.append(line)
    return patterns


def _is_ignored(name: str, patterns: list[str]) -> bool:
    return any(fnmatch.fnmatch(name, pattern) for pattern in patterns)


def shipped_top_level_modules(root: Path) -> list[str]:
    """Top-level .py modules that land in the deployment bundle."""
    patterns = _nxdignore_patterns(root)
    return sorted(
        path.stem
        for path in root.glob("*.py")
        if path.name != "__init__.py" and not _is_ignored(path.name, patterns)
    )


def _declared_py_modules(root: Path) -> list[str]:
    """`py-modules` out of [tool.setuptools], read without a TOML parser.

    tomllib landed in 3.11 and the skill targets 3.10, so this reads the array
    textually. It is deliberately permissive: a py-modules block it cannot parse
    is reported as no block rather than assumed correct.
    """
    path = root / "pyproject.toml"
    if not path.exists():
        return []
    text = path.read_text()
    match = re.search(r"py-modules\s*=\s*\[(.*?)\]", text, re.DOTALL)
    if not match:
        return []
    return re.findall(r"[\"']([^\"']+)[\"']", match.group(1))


def check_flat_layout(root: Path) -> list[Finding]:
    modules = shipped_top_level_modules(root)
    if len(modules) <= 1:
        return []
    if (root / "__init__.py").exists():
        return []

    declared = _declared_py_modules(root)
    missing = [module for module in modules if module not in declared]
    if not declared:
        return [
            Finding(
                ERROR,
                "flat-layout",
                "pyproject.toml",
                f"{len(modules)} top-level modules ship ({', '.join(modules)}) with no packaging "
                "guard. Add [tool.setuptools] py-modules listing them, or an empty __init__.py at "
                "the product root. Without one, nxd launch fails at 'Installing dependencies' with "
                "'Multiple top-level modules discovered in a flat-layout'.",
            )
        ]
    if missing:
        return [
            Finding(
                ERROR,
                "flat-layout",
                "pyproject.toml",
                f"py-modules omits shipped module(s): {', '.join(missing)}.",
            )
        ]
    return []


def bindable_names(root: Path) -> set[str]:
    """Names a contract or transform parameter may legitimately carry.

    Service names from `.service(service_name=...)`, plus input and port names,
    since a reader cannot tell from the contract file alone which spelling the
    author wired. Hyphens normalise to underscores, as they do in the signature.
    """
    spec = root / "spec.py"
    if not spec.exists():
        return set()
    text = spec.read_text()
    names: set[str] = set()
    for pattern in (
        r"service_name\s*=\s*[\"']([^\"']+)[\"']",
        r"\.port\(\s*[\"']([^\"']+)[\"']",
        r"\.input\(\s*[\"']([^\"']+)[\"']",
    ):
        names.update(re.findall(pattern, text))
    return {name.replace("-", "_") for name in names}


def _verify_functions(tree: ast.Module) -> list[ast.FunctionDef]:
    return [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == "verify"
    ]


def _mentions_failure(tree: ast.Module) -> bool:
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and node.attr in {"FAILED", "WARNING"}:
            return True
    return False


def check_contracts(root: Path) -> list[Finding]:
    contracts = root / "contracts"
    if not contracts.is_dir():
        return []

    acceptable = bindable_names(root)
    findings: list[Finding] = []

    for path in sorted(contracts.glob("*.py")):
        if path.name == "__init__.py":
            continue
        try:
            tree = ast.parse(path.read_text())
        except SyntaxError as exc:
            findings.append(
                Finding(ERROR, "verify-bind", str(path), f"could not parse: {exc}")
            )
            continue

        functions = _verify_functions(tree)
        if not functions:
            findings.append(
                Finding(
                    ERROR,
                    "verify-bind",
                    f"{path}",
                    "no verify() function found; a contract script must define one.",
                )
            )
            continue

        for function in functions:
            args = function.args.args
            if not args:
                findings.append(
                    Finding(
                        ERROR,
                        "verify-bind",
                        f"{path}:{function.lineno}",
                        "verify() takes no service context parameter.",
                    )
                )
                continue

            first = args[0].arg
            if acceptable and first not in acceptable:
                findings.append(
                    Finding(
                        ERROR,
                        "verify-bind",
                        f"{path}:{function.lineno}",
                        f"verify()'s first parameter is '{first}', which matches no declared "
                        f"service, input or port. Arguments bind by name, not position. "
                        f"Expected one of: {', '.join(sorted(acceptable))}.",
                    )
                )

        if not _mentions_failure(tree):
            findings.append(
                Finding(
                    ERROR,
                    "verify-weak",
                    f"{path}",
                    "never references VerifyResultEnum.FAILED or .WARNING, so it can only return "
                    "PASS and asserts nothing at runtime.",
                )
            )

    return findings


def _spec_version(root: Path) -> str | None:
    spec = root / "spec.py"
    if not spec.exists():
        return None
    match = re.search(r"version\s*=\s*[\"']([^\"']+)[\"']", spec.read_text())
    return match.group(1) if match else None


def _pyproject_version(root: Path) -> str | None:
    path = root / "pyproject.toml"
    if not path.exists():
        return None
    match = re.search(r"^\s*version\s*=\s*[\"']([^\"']+)[\"']", path.read_text(), re.MULTILINE)
    return match.group(1) if match else None


def check_version_coherence(root: Path) -> list[Finding]:
    spec_version = _spec_version(root)
    project_version = _pyproject_version(root)
    if not spec_version or not project_version:
        return []
    if spec_version != project_version:
        return [
            Finding(
                WARN,
                "version-drift",
                "pyproject.toml",
                f"pyproject version '{project_version}' differs from spec.py version "
                f"'{spec_version}'. Reconcile them, or record why they differ in the README.",
            )
        ]
    return []


# Modifiers that change who can reach the data or how access is granted. Each is
# legitimate when asked for and a liability when added to look thorough, so the
# check asks for a justification rather than forbidding them.
ACCESS_MODIFIERS = frozenset(
    {
        "managed_access",
        "access_approval",
        "access_control",
        "skip_approval_flow",
        "follow_approval_flow",
        "enable_public_access",
        "enable_temporal_credentials",
        "disable_temporal_credentials",
        "request_on_behalf_of",
        "without_default_access_approval",
    }
)


def _justification_text(root: Path) -> str:
    """Prose the author wrote about this product, where a rationale would live."""
    parts = []
    for name in ("README.md", "REQUIREMENTS_CHECKLIST.md"):
        path = root / name
        if path.exists():
            parts.append(path.read_text())
    return "\n".join(parts)


def check_unrequested_surface(root: Path) -> list[Finding]:
    """Flag deployed-behaviour modifiers that no prose in the product justifies.

    Intent is not mechanically knowable: this cannot tell a requested
    `.managed_access()` from an invented one. So it reports WARN and asks for the
    rationale to exist in writing, which is the part a reviewer can check.

    An executor or cluster config is told apart from a storage config by shape:
    storage configs are calls (`adls_config(...)`), executor configs are bare
    names (`k8s_executor_config`, `cluster_config`).
    """
    spec = root / "spec.py"
    if not spec.exists():
        return []

    try:
        tree = ast.parse(spec.read_text())
    except SyntaxError as exc:
        return [Finding(ERROR, "surface", "spec.py", f"could not parse: {exc}")]

    justification = _justification_text(root)
    findings: list[Finding] = []

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
            continue
        attr = node.func.attr

        if attr in ACCESS_MODIFIERS:
            if attr in justification:
                continue
            findings.append(
                Finding(
                    WARN,
                    "surface",
                    f"spec.py:{node.lineno}",
                    f".{attr}() changes access semantics and no README or checklist line "
                    "mentions it. Confirm it was asked for and record why, or drop it and "
                    "take the platform default.",
                )
            )
            continue

        if attr == "config" and node.args and isinstance(node.args[0], ast.Name):
            name = node.args[0].id
            if name in justification:
                continue
            findings.append(
                Finding(
                    WARN,
                    "surface",
                    f"spec.py:{node.lineno}",
                    f".config({name}) pins executor or cluster behaviour (resources, timeouts) "
                    "and no README or checklist line mentions it. Confirm it was asked for and "
                    "record why, or drop it and take the platform default.",
                )
            )

    return findings


# The contract executor. The platform selects it on its own and excludes it from
# service resolution ("it is not an infra-profile service", nxd/spec/_spec.py), so
# naming it in `.service(driver=...)` resolves the context to a bare `Context`.
CONTRACT_EXECUTOR_DRIVER_MARKER = "kubernetes/contract"


def check_contract_driver(root: Path) -> list[Finding]:
    """Flag `.service(driver=...)` carrying the contract executor driver.

    `driver=` selects the context class handed to the contract. Passing the
    executor driver yields a bare `Context` with no `model_paths`, `container` or
    credentials, so a contract that reads anything raises at verification time.
    Invisible to `nxd validate`, which accepts any driver string, and invisible to
    a contract that returns PASS without touching its context.
    """
    spec = root / "spec.py"
    if not spec.exists():
        return []

    findings: list[Finding] = []
    for number, line in enumerate(spec.read_text().splitlines(), start=1):
        if "service_name" not in line and ".service(" not in line:
            continue
        for driver in re.findall(r"driver\s*=\s*[\"\']([^\"\']+)[\"\']", line):
            if CONTRACT_EXECUTOR_DRIVER_MARKER in driver:
                findings.append(
                    Finding(
                        ERROR,
                        "contract-driver",
                        f"spec.py:{number}",
                        f"driver='{driver}' is the contract executor, which the platform selects "
                        "itself and which is not an infra-profile service. It resolves to a bare "
                        "Context, so every attribute access in the contract fails at verification "
                        "time. Use the storage driver the profile declares for this service.",
                    )
                )
    return findings


def run_checks(root: Path) -> list[Finding]:
    return [
        *check_flat_layout(root),
        *check_contracts(root),
        *check_version_coherence(root),
        *check_contract_driver(root),
        *check_unrequested_surface(root),
    ]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("directory", help="data product directory to check")
    args = parser.parse_args(argv)

    root = Path(args.directory).resolve()
    if not root.is_dir():
        print(f"not a directory: {root}", file=sys.stderr)
        return 2

    findings = run_checks(root)
    if not findings:
        print(f"preflight: clean ({root})")
        return 0

    for finding in findings:
        print(finding.render())

    errors = sum(1 for finding in findings if finding.level == ERROR)
    warnings = len(findings) - errors
    print(f"\npreflight: {errors} error(s), {warnings} warning(s)")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())

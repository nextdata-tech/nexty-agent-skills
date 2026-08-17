"""Pin the ``EVAL_*`` names ``run.py`` reads to the names the docs tell operators to set.

An environment variable is a contract between code and a human following setup
instructions. Nothing links the two: rename it on one side and there is no broken
import and no failing assert — the runner just reads an unset variable and takes
its "not configured" branch, while the operator swears they exported it.

That is not hypothetical. PR #148 renamed this variable in the docs but left
``run.py`` reading ``EVAL_JOB_PYTHON``; the six desktop scenarios are ``ci_skip``'d,
so the mismatch survived a review round and a ledger entry claiming it was fixed.

Kept deliberately narrow: only variables the runner *reads* must be documented.
Docs may describe extra variables consumed elsewhere (checkers, backends, CI).
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EVALS = ROOT / "evals"
RUN_PY = EVALS / "run.py"
DOCS = (EVALS / "GETTING-STARTED.md", EVALS / "README.md")

_ENV_NAME = re.compile(r"EVAL_[A-Z0-9_]+")

# Prefixes built by string concatenation rather than read whole, so they name no
# single variable an operator could export.
_PREFIX_FRAGMENTS = {"EVAL_MCP_"}


def _names_read_by_runner() -> set[str]:
    """``EVAL_*`` names that *appear* anywhere in ``run.py``.

    A deliberate superset of the names it actually reads: comments and error
    strings count too. That errs toward over-requiring documentation, which is
    the safe direction here — a documented name that is never read costs a stale
    doc line, while an undocumented name that *is* read costs a silent
    misconfiguration.

    The regex cannot see a name assembled by concatenation, which is why
    ``_PREFIX_FRAGMENTS`` exempts the ``EVAL_MCP_`` stem. A second such prefix
    would fail this test spuriously rather than being handled; add it there.
    """
    text = RUN_PY.read_text(encoding="utf-8")
    found = {
        name
        for name in _ENV_NAME.findall(text)
        if name not in _PREFIX_FRAGMENTS
    }
    return found


def _names_in_docs() -> set[str]:
    names: set[str] = set()
    for doc in DOCS:
        if doc.exists():
            names |= set(_ENV_NAME.findall(doc.read_text(encoding="utf-8")))
    return names


def test_every_env_var_the_runner_reads_is_documented() -> None:
    """A variable the runner reads but no doc names cannot be set correctly.

    The operator-visible symptom is a scenario that reports itself unconfigured
    while the documented variable is exported — the shape that hid the
    ``EVAL_JOB_PYTHON`` / ``EVAL_DESKTOP_PYTHON`` split.
    """
    undocumented = sorted(_names_read_by_runner() - _names_in_docs())
    assert not undocumented, (
        "run.py reads these EVAL_* variables but no file in evals/ documents them, "
        "so an operator has no way to learn the name — likely a rename applied to "
        f"the docs but not the runner (or vice versa): {undocumented}"
    )


def test_desktop_python_var_agrees_across_every_surface() -> None:
    """The desktop interpreter variable has one spelling everywhere.

    Pinned by name because it is the one that broke, it spans the most surfaces
    (runner, both scenario READMEs, ``ci_skip`` messages, a checker, the
    architecture doc), and every surface fails silently when they disagree.
    """
    canonical = "EVAL_DESKTOP_PYTHON"
    stale = "EVAL_JOB_PYTHON"

    runner = RUN_PY.read_text(encoding="utf-8")
    assert stale not in runner, (
        f"run.py still reads {stale}; the documented name is {canonical}"
    )
    assert canonical in runner, f"run.py no longer reads {canonical}"

    offenders: list[str] = []
    for path in sorted(EVALS.rglob("*")):
        if not path.is_file() or path.suffix not in {".py", ".md", ".json"}:
            continue
        if "benchmarks" in path.parts:  # frozen evidence keeps its original text
            continue
        if path.resolve() == Path(__file__).resolve():
            continue  # this file names the stale spelling in order to forbid it
        if stale in path.read_text(encoding="utf-8", errors="ignore"):
            offenders.append(str(path.relative_to(ROOT)))
    assert not offenders, f"stale {stale} spelling survives in: {offenders}"


def _leading_string_literals(node: ast.AST) -> list[str]:
    """The literal text a value would start with, for str and f-string forms."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return [node.value]
    if isinstance(node, ast.JoinedStr):
        for part in node.values:  # only the FIRST part sets the leading case
            if isinstance(part, ast.Constant) and isinstance(part.value, str):
                return [part.value]
            return []  # starts with an interpolation — no literal case to judge
    return []


def _res_error_literals() -> list[str]:
    """Strings assigned to ``res.error``, plus the helper returns interpolated in.

    Parsed with ``ast`` rather than regexed, so single quotes, ``rf`` prefixes and
    odd whitespace cannot slip a non-conforming form past the check — the test
    fails closed on a form it does not recognize rather than silently skipping it.
    """
    tree = ast.parse(RUN_PY.read_text(encoding="utf-8"))
    found: list[str] = []

    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if (
                    isinstance(target, ast.Attribute)
                    and target.attr == "error"
                    and isinstance(target.value, ast.Name)
                    and target.value.id == "res"
                ):
                    found += _leading_string_literals(node.value)

    # Helpers whose return value is interpolated into res.error verbatim; their
    # literals render mid-sentence and follow the same convention.
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name.endswith(
            "_infrastructure_error"
        ):
            for inner in ast.walk(node):
                if isinstance(inner, ast.Return) and inner.value is not None:
                    found += _leading_string_literals(inner.value)

    return found


def test_res_error_literals_are_lowercase() -> None:
    """Every string reaching ``res.error`` starts lowercase.

    ``res.error`` renders through two sinks that treat it as an opaque whole —
    ``f"✗ ERROR — {res.error}"`` and the JSON report's ``"error"`` field — and the
    field's long-standing convention is lowercase (``"missing checks.json"``,
    ``"agent run failed"``, ``"http stub setup failed: …"``). A codename sweep
    capitalized three of them on an invented "sentence-initial" rule, and the
    drift took three review rounds to unwind because nothing asserted it.

    Covers the ``*_infrastructure_error`` helper returns too: those are
    interpolated into ``res.error`` verbatim, so they render mid-sentence and are
    the same contract. Checking only direct assignments would leave a hole at
    exactly the strings the correcting PR had to edit.

    Acronym-initial values (``MCP server setup failed``) are the one exception.
    """
    bad = [
        lit for lit in _res_error_literals()
        if lit[:1].isupper() and not re.match(r"^[A-Z]{2,}\b", lit)
    ]
    assert not bad, (
        "string(s) reaching res.error that start with a capital; the field's "
        f"convention is lowercase (acronyms excepted): {bad}"
    )


def test_runner_class_names_are_capitalized() -> None:
    """No ``class`` in ``run.py`` starts lowercase.

    A blanket ``Pocket`` → ``desktop`` substitution lowercased ``PocketServe`` to
    ``desktopServe``. Nothing breaks — it is applied consistently — so only a
    reader notices, which is why it survived one review round and a re-apply.
    Cheap to pin, and it generalizes past this one name.
    """
    bad = re.findall(r"^class ([a-z][A-Za-z0-9_]*)", RUN_PY.read_text(encoding="utf-8"), re.M)
    assert not bad, (
        "lowercase class name(s) in run.py, likely an artifact of a case-insensitive "
        f"rename sweep: {sorted(set(bad))}"
    )


def test_desktop_supervisor_var_agrees_with_its_sibling() -> None:
    """The two desktop variables share a prefix, so a rename must move both.

    They are always exported together; a half-applied rename leaves the pair
    inconsistent and the failure message naming a variable no doc mentions.
    """
    runner = RUN_PY.read_text(encoding="utf-8")
    for name in ("EVAL_DESKTOP_SUPERVISOR_DIR", "EVAL_DESKTOP_PYTHON"):
        assert name in runner, f"run.py no longer reads {name}"
        assert name in _names_in_docs(), f"{name} is read by run.py but undocumented"

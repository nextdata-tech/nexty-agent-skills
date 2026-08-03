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
    """``EVAL_*`` names ``run.py`` passes to os.environ."""
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

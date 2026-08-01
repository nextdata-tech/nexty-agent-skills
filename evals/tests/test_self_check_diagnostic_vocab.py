"""CONSTRAINT-1: `self_check.py` inlines its vocabulary and must not drift.

`scripts/self_check.py` is copied INTO a closure and run there, so it can never
import `dp_diagnostics.py` — the closure has no `scripts/` beside it. It carries
a literal `dict` and `json.dumps` instead. That is the right trade, and it has
one cost: two copies of the vocabulary that can drift apart silently.

This test is what stops the drift. It walks the script for code and stage
literals and asserts every one of them exists in the shared registry. It does
NOT require the converse — `self_check.py` legitimately produces only a subset
of the codes, and the registry deliberately carries codes no script produces yet.
"""

from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SCRIPTS = REPO / "scripts"
SELF_CHECK = SCRIPTS / "self_check.py"

# `dp_diagnostics.py` ships INSIDE the skill tree so the installer carries it;
# `self_check.py` stays at the repo root because it is copied into the closure
# and run there, never installed. Two locations, deliberately.
SKILL_SCRIPTS = REPO / "src" / "nxd-pocket-loop" / "scripts"

if str(SKILL_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SKILL_SCRIPTS))

import dp_diagnostics as dpd  # noqa: E402

DOMAINS = sorted({code.split(".")[0] for code in dpd.CODES})
STAGE_RE = re.compile(r"^s[0-9]_[a-z_]+$")
NOT_A_CODE = (".py", ".md", ".json", ".yaml", ".yml", ".csv", ".txt")


def _string_constants(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return [
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    ]


def test_self_check_never_imports_the_shared_module():
    """It runs inside a closure, where `dp_diagnostics` does not exist."""
    source = SELF_CHECK.read_text(encoding="utf-8")
    assert "import dp_diagnostics" not in source
    assert "from dp_diagnostics" not in source


def test_every_code_literal_is_registered():
    unknown = []
    for value in _string_constants(SELF_CHECK):
        if value.endswith(NOT_A_CODE) or not dpd.CODE_RE.match(value):
            continue
        if value.split(".")[0] not in DOMAINS:
            continue
        if value not in dpd.CODES:
            unknown.append(value)
    assert not unknown, (
        "self_check.py emits diagnostic codes that are not in "
        f"dp_diagnostics.CODES: {sorted(set(unknown))}"
    )


def test_every_stage_literal_is_a_real_stage():
    unknown = [
        value
        for value in _string_constants(SELF_CHECK)
        if STAGE_RE.match(value) and value not in dpd.STAGES
    ]
    assert not unknown, f"self_check.py names stages that do not exist: {sorted(set(unknown))}"


def test_self_check_only_claims_stages_it_can_produce():
    """Phases A, B and C+D — never a stage that needs a supervisor."""
    named = {v for v in _string_constants(SELF_CHECK) if v in dpd.STAGES}
    illegal = named - set(dpd.REPORT_TOOLS["self_check"])
    assert not illegal, (
        f"self_check.py names stage(s) it cannot produce: {sorted(illegal)}"
    )

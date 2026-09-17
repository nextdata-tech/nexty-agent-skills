"""Pin the reviewer's boundary between structural notes and claims."""

from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
REVIEW_SKILL = REPO_ROOT / "src" / "nxd-review-closure" / "SKILL.md"


def _review_scope() -> str:
    text = REVIEW_SKILL.read_text(encoding="utf-8")
    start = text.index("## Structural notes versus claims")
    end = text.index("## Return findings as claims, not verdicts")
    return " ".join(text[start:end].split())


def test_internal_documentation_nits_are_structural_notes():
    scope = _review_scope()

    for marker in (
        "comments",
        "docstrings",
        "formatting",
        "internal-only citations or cross-references",
        "one-line `structural_note`",
        "not a `HIGH`, `MEDIUM`, or `LOW` claim",
        "no effect on consumer correctness",
        "a public promise or contract",
        "discoverability or queryability",
        "runtime or operational behavior",
        "Do not return a finding object for those nits",
    ):
        assert marker in scope, f"reviewer scope contract lost: {marker}"


def test_public_consumer_and_behavior_documentation_remain_claims():
    """Negative controls prevent the structural-note carve-out becoming broad."""
    scope = _review_scope()

    for marker in (
        "remains a claim",
        "mislead a consumer or operator",
        "conceal a violation of a public promise or contract",
        "affect expected behavior",
        "public model or field description",
        "operator instruction",
        "unsupported action",
        "hides a supported access path",
        "concrete impact",
    ):
        assert marker in scope, f"negative control missing: {marker}"


def test_low_and_why_it_matters_keep_consumer_impact_requirements():
    text = " ".join(REVIEW_SKILL.read_text(encoding="utf-8").split())
    severity_start = text.index("- `severity`")
    severity_end = text.index("- `claim`", severity_start)
    why_start = text.index("- `why_it_matters`")
    why_end = text.index("Rank most severe first", why_start)
    severity = text[severity_start:severity_end]
    why_it_matters = text[why_start:why_end]

    assert "real consumer-facing or public-contract quality defect" in severity
    assert "limited impact" in severity
    assert "never a style, formatting, or internal-reference nit" in severity
    assert "a concrete consumer or operator consequence" in why_it_matters
    assert "Do not write a generic quality complaint" in why_it_matters
    assert "merely restate the claim" in why_it_matters

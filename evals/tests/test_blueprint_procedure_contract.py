"""The blueprint must say where a resolved procedure value lives.

The policy gate already names the gap class generically — "a scale defining only
some levels (5 and 1 given, 2/3/4 absent)" — so the pack knows to ask. What was
missing is the other half: once the user answers, nothing required the answer to
land anywhere durable, so a resolved threshold could legally become a literal in
`transform/main.py`. Prose then travelled to the next reader and the executable
logic did not.

A conversational gate cannot cover this on its own. It fires once, in one
session, and not at all on a blueprint that was already approved with the gap
inside it — which is exactly how a rubric with two prose anchors and no bands
reached a closure that hardcoded them.

These pin the structural half, so the rule cannot quietly disappear from the
document that authors actually read.
"""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
BLUEPRINT = (REPO_ROOT / "src" / "nxd-run-job-loop" / "reference" /
             "dp-blueprint.md")
GENERATOR = (REPO_ROOT / "src" / "nxd-generate-data-product" / "SKILL.md")


def _blueprint() -> str:
    return BLUEPRINT.read_text(encoding="utf-8")


def test_blueprint_requires_procedure_values_to_be_a_landed_model():
    t = _blueprint()
    assert "Procedures are landed, not described" in t, (
        "dp-blueprint.md must carry the rule that a procedure's executable "
        "values are a landed model — without it a resolved threshold legally "
        "becomes a transform literal"
    )
    assert "landed model declared in `Models`" in t, (
        "the rule must name where the values go, not merely that they matter"
    )
    assert "band id" in t, (
        "the model needs an addressable band id; a prose justification cannot "
        "be grouped, counted, or diffed across runs"
    )


def test_blueprint_states_the_underspecified_scale_test():
    """The reader needs a test they can apply, not just a principle."""
    t = _blueprint()
    assert "predict the result for a case" in t, (
        "the rule must give a falsifiable test for underspecification"
    )
    assert "anchors written for 5 and 1" in t, (
        "the worked instance of an underspecified scale must appear, since it "
        "is the shape the policy gate enumerates"
    )


def test_blueprint_requires_a_clock_relative_term_to_name_its_anchor():
    t = _blueprint()
    assert "must name its anchor" in t, (
        "a Term defined against now/today/fetch time cannot be computed: a "
        "derived model may not call now()"
    )
    assert "now()" in t and "Decisions" in t, (
        "the rule must say why (no clock in a derived model) and where the "
        "choice is recorded"
    )


def test_the_policy_gate_points_at_where_the_answer_goes():
    """The gate and the representation rule must sit next to each other.

    Asking without saying where the answer lives is how the original defect
    happened: the gate fired, the user answered, and the answer became a literal.
    """
    t = GENERATOR.read_text(encoding="utf-8")
    assert "Procedures are landed, not described" in t, (
        "the generator's policy gate must point at the blueprint rule; the ask "
        "and the destination belong together"
    )

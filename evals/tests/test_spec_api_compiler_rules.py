"""Two compiler rules that `nxd-spec-api.md` is the only place to learn.

Neither is visible to the offline self-check: its structural phase parses
`models.py` against the DSL surface and passes on both, so they surface only
when the supervisor compiles `spec.py`. That makes this file the sole carrier,
and this file's own "Version pin and drift" section warns that a pinned surface
description rots silently.

These are doc contracts, not behaviour tests — the behaviour lives in the
compiler, which is not importable here. They exist so a later edit cannot delete
a rule that cost a build round-trip each to rediscover.
"""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SPEC_API = (REPO_ROOT / "src" / "nxd-generate-data-product" / "reference" /
            "nxd-spec-api.md")
SKILL = REPO_ROOT / "src" / "nxd-generate-data-product" / "SKILL.md"
SEMANTIC_SKILL = REPO_ROOT / "src" / "nxd-build-semantic-data-product" / "SKILL.md"


def _doc() -> str:
    return SPEC_API.read_text(encoding="utf-8")


def test_dimension_names_are_documented_as_registry_wide():
    t = _doc()
    assert "unique across the join-connected registry" in t, (
        "dimension names collide across models a join relates; without this a "
        "second model declaring `created_at` fails to compile with no warning "
        "in the file authors are told to trust"
    )
    assert "Duplicate dimension name" in t, (
        "quote the compiler's own error so a reader can match what they saw"
    )


def test_the_dimension_rule_says_to_tag_every_dimension():
    """Renaming only observed collisions is not closed under itself."""
    t = _doc()
    assert "Tag every" in t and "rather" in t, (
        "the guidance must be to tag every dimension by model, not to rename "
        "the collisions already reported"
    )
    assert "judgment_status" in t, (
        "keep the worked case where a tag invented for one collision landed on "
        "a real column of another model"
    )


def test_join_must_cover_the_target_grain():
    t = _doc()
    assert "must cover the target model's `primary_key()`" in t, (
        "a join onto a merely-unique column double-counts measures"
    )
    assert "not cover that model's grain" in t, (
        "quote the compiler's own error"
    )


def test_the_offline_blind_spot_is_stated():
    """A reader who trusts the self-check needs to know it cannot see these."""
    t = _doc()
    assert "Neither rule is visible offline" in t
    assert "check_data_product" in t, (
        "name what does report them, or the reader has nowhere to go"
    )


def test_timestamp_requires_an_explicit_duration_unit():
    t = _doc()
    assert "timestamp(unit=DurationUnit.Milliseconds)" in t, (
        "datetime fields need a concrete, copyable timestamp declaration"
    )
    assert "timestamp / datetime" in t, (
        "the inferred-type mapping must cover API/source datetime values"
    )
    assert "`timestamp()` raises `TypeError` during supervisor spec compilation" in t
    assert "`timestamp()`" not in t.replace(
        "`timestamp()` raises `TypeError` during supervisor spec compilation", ""
    ), "the normative API reference must not carry a bare timestamp call"


def test_semantic_inference_maps_timestamp_to_the_parameterized_type():
    t = SEMANTIC_SKILL.read_text(encoding="utf-8")
    assert "import `DurationUnit` from" in t
    assert "`nxd.spec.data_types`" in t
    assert "`TIMESTAMP` / `TIMESTAMPTZ`" in t
    assert "timestamp(unit=DurationUnit.Milliseconds)" in t
    assert "| `TIMESTAMP` / `TIMESTAMPTZ` | `timestamp()` |" not in t


def test_semantic_views_use_the_output_model_chain_and_count_is_documented():
    t = _doc()
    assert "Never call this for a `semantic_view`" in t, (
        "semantic views must be registered on data_product_output(), never "
        "promised as physical tables"
    )
    assert "Use this same registration for a physical model whose" in t
    skill = SKILL.read_text(encoding="utf-8")
    assert '.model(view)' in skill and 'metric(Agg.COUNT, column="*"' in skill, (
        "aggregate-only products need the public COUNT(*) metric shape"
    )


def test_models_only_declares_landed_outputs_and_query_surfaces():
    skill = SKILL.read_text(encoding="utf-8")
    assert "Declare only physical output models in `models.py`." in skill, (
        "source-only semantic models violate the models/spec/PHYSICAL_MODELS "
        "naming invariant and fail the trusted self-check"
    )
    assert "source-only/staging-only" in skill
    assert "Every query-facing promised model needs a semantic view." in skill, (
        "a physical output without a registered semantic view cannot be selected "
        "by run_semantic_query"
    )


def test_the_note_does_not_break_the_role_builder_list():
    """A blank line plus an unindented paragraph ends a CommonMark list.

    Placed between two bullets it splits the six role builders into two lists
    and reads as an introduction to the ones below it. The file's convention is
    to put a section-level note after the complete list.
    """
    t = _doc()
    note = t.index("**Neither rule is visible offline.**")
    last_bullet = t.index("- **`metric_field(dtype, metric_role")
    assert note > last_bullet, (
        "the offline-blind-spot note must follow the last role-builder bullet, "
        "not sit between two of them"
    )

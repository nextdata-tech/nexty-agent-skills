"""Extraction tests for the documentation baseline boundary."""

from __future__ import annotations

from pathlib import Path
import shutil

import pytest

from _repo_paths import REPO_ROOT

from dp_scenarios.canary.claims import Baseline, ClaimsDocument, claims_content_hash, document_json, load_claims
from dp_scenarios.canary.extract import ClaimDriftError, extract_claims, source_skill_files


def _fixture_tree(tmp_path: Path) -> Path:
    root = tmp_path / "skills"
    skill = root / "fixture-skill"
    (skill / "reference").mkdir(parents=True)
    (skill / "SKILL.md").write_text(
        "# Fixture\n"
        "CANARY_CLAIM id=api-shape code=runtime/transform_import direction=documented-supported kind=secret :: flat map\n"
        "CANARY_CLAIM id=median code=structure/spec_compile_failed direction=documented-unsupported kind=unsupported :: median\n",
        encoding="utf-8",
    )
    (skill / "reference" / "shape.md").write_text("A reference source text.\n", encoding="utf-8")
    return root


def _approved(extracted) -> ClaimsDocument:
    claim_hash = claims_content_hash(extracted.claims)
    return ClaimsDocument(
        extracted.claims,
        Baseline(extracted.baseline.skill_files, "fixture-reviewer", "2026-08-17", claim_hash),
        {
            "reviewer": "fixture-reviewer",
            "review_date": "2026-08-17",
            "old_claims_hash": claim_hash,
            "new_claims_hash": claim_hash,
        },
    )


def test_extraction_round_trips_committed_fixture_claims(tmp_path: Path) -> None:
    root = _fixture_tree(tmp_path)
    first = extract_claims(root)
    committed = tmp_path / "claims.json"
    committed.write_text(document_json(_approved(first)), encoding="utf-8")

    checked = extract_claims(root, existing=_approved(first))

    assert source_skill_files(root) == (
        root / "fixture-skill" / "SKILL.md",
        root / "fixture-skill" / "reference" / "shape.md",
    )
    assert checked.claims == first.claims
    assert checked.drift == ()


def test_committed_canary_claims_match_repository_skills() -> None:
    repo_root = REPO_ROOT
    claims_path = repo_root / "evals/dp-scenarios/scenarios/drift-canary/claims.json"

    checked = extract_claims(
        repo_root / "src",
        existing=load_claims(claims_path),
        fail_on_drift=False,
    )

    assert checked.drift == ()


def test_one_byte_source_span_change_is_a_drift_finding(tmp_path: Path) -> None:
    root = _fixture_tree(tmp_path)
    first = extract_claims(root)
    skill_file = root / "fixture-skill" / "SKILL.md"
    original = skill_file.read_text(encoding="utf-8")
    skill_file.write_text(original.replace("flat map", "flat nap", 1), encoding="utf-8")

    with pytest.raises(ClaimDriftError) as raised:
        extract_claims(root, existing=_approved(first))

    assert any("api-shape" in finding.claim_id for finding in raised.value.findings)
    span = next(
        finding
        for finding in raised.value.findings
        if "api-shape" in finding.claim_id and "quoted source span" in finding.reason
    )
    assert span.before.endswith("flat map")
    assert span.after.endswith("flat nap")
    assert "fixture-skill/SKILL.md:2" in str(raised.value)


def test_claim_ids_are_relative_and_survive_unrelated_line_insertion(tmp_path: Path) -> None:
    root = _fixture_tree(tmp_path)
    first = extract_claims(root)
    original = (root / "fixture-skill" / "SKILL.md").read_text(encoding="utf-8")
    (root / "fixture-skill" / "SKILL.md").write_text("# inserted prose\n" + original, encoding="utf-8")

    checked = extract_claims(root, existing=_approved(first))

    assert checked.drift == ()
    assert all(not claim.skill_file.startswith("/") for claim in checked.claims)
    assert {claim.claim_id for claim in checked.claims} == {claim.claim_id for claim in first.claims}


def test_claim_free_file_change_is_only_an_advisory(tmp_path: Path) -> None:
    root = _fixture_tree(tmp_path)
    first = extract_claims(root)
    reference = root / "fixture-skill" / "reference" / "shape.md"
    reference.write_text("A different reference source text.\n", encoding="utf-8")

    checked = extract_claims(root, existing=_approved(first))

    assert checked.drift == ()
    assert checked.advisories == ()


def test_byte_identical_tree_at_another_root_has_no_path_drift(tmp_path: Path) -> None:
    root = _fixture_tree(tmp_path)
    first = extract_claims(root)
    copy = tmp_path / "copied-skills"
    shutil.copytree(root, copy)

    checked = extract_claims(copy, existing=_approved(first))

    assert checked.drift == ()
    assert [claim.claim_id for claim in checked.claims] == [claim.claim_id for claim in first.claims]
    assert all(not claim.skill_file.startswith("/") for claim in checked.claims)


def test_symlinked_skills_root_uses_one_resolved_path(tmp_path: Path) -> None:
    root = _fixture_tree(tmp_path)
    first = extract_claims(root)
    link = tmp_path / "linked-skills"
    link.symlink_to(root, target_is_directory=True)

    checked = extract_claims(link, existing=_approved(first))

    assert checked.drift == ()
    assert checked.claims == first.claims


def test_ambiguous_prefix_falls_back_to_nearby_file_category_and_line(tmp_path: Path) -> None:
    root = tmp_path / "skills"
    skill = root / "fixture-skill"
    skill.mkdir(parents=True)
    source = skill / "SKILL.md"
    source.write_text(
        "CANARY_CLAIM id=shared code=runtime/shape direction=documented-supported kind=secret :: first\n"
        "CANARY_CLAIM id=shared code=runtime/shape direction=documented-supported kind=secret :: second\n",
        encoding="utf-8",
    )
    first = extract_claims(root)
    source.write_text(source.read_text(encoding="utf-8").replace("first", "changed", 1), encoding="utf-8")

    checked = extract_claims(root, existing=_approved(first), fail_on_drift=False)

    span = next(finding for finding in checked.drift if "quoted source span" in finding.reason)
    assert span.before.endswith("first")
    assert span.after.endswith("changed")
    assert span.line == 1


def test_extraction_ignores_code_examples_and_non_marker_prose(tmp_path: Path) -> None:
    root = tmp_path / "skills"
    skill = root / "fixture-skill"
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text(
        "```python\nsemantic_model(\"example\")\n```\n"
        "A paragraph mentioning semantic_view(...) is not a claim.\n"
        "CANARY_CLAIM id=explicit code=runtime/import_failed direction=documented-supported :: exact\n",
        encoding="utf-8",
    )

    result = extract_claims(root)

    assert len(result.claims) == 1
    assert result.claims[0].claim_id.startswith("fixture-skill/SKILL.md:explicit:")


def test_connector_table_is_only_a_type_claim(tmp_path: Path) -> None:
    root = tmp_path / "skills"
    skill = root / "fixture-skill"
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text(
        "| CSV (proven) | `csv-source` | `csv_source` | `csv-source-path` + `data/` |\n"
        "- Transform secrets key: `secrets[\"file_source\"]` — a string\n"
        "- Companion file: `file-source-path` — one line\n"
        "| the connector's per-model reference | `data/<name>/` for a file connector | yes | no |\n"
        "└── data/              # the connector export: data/<base_model>/*.csv\n"
        "Same per-model layout as CSV: one subdirectory per model under the file-source root, `data/<model>/*.<ext>`.\n",
        encoding="utf-8",
    )

    result = extract_claims(root)

    assert [claim.category for claim in result.claims] == [
        "type",
        "secret",
        "companion",
        "directory",
        "directory",
    ]
    assert result.claims[0].expected_finding_code == "structure/spec_compile_failed"
    assert result.claims[1].expected_finding_code == "build/transform_import"
    assert result.claims[2].expected_finding_code == "structure/companion_files_invalid"
    assert all(
        claim.skill_file.endswith("SKILL.md")
        for claim in result.claims
        if claim.category == "directory"
    )


def test_canonical_source_types_index_rows_are_type_claims(tmp_path: Path) -> None:
    root = tmp_path / "skills"
    reference = root / "fixture-skill" / "reference"
    reference.mkdir(parents=True)
    (root / "fixture-skill" / "SKILL.md").write_text(
        "See the [source types index](reference/source-types.md) for the canonical matrix.\n",
        encoding="utf-8",
    )
    (reference / "source-types.md").write_text(
        "| Source type | Service | Companion artifact | Detailed recipe |\n"
        "|---|---|---|---|\n"
        "| CSV | `csv-source` | `csv-source-path` + `data/` | [CSV](../SKILL.md) |\n"
        "| Other local file | `file-source` | `file-source-path` + `data/` | [File](file-source.md) |\n"
        "| Database | `db-source` | `db-source-tables` | [Database](database-source.md) |\n"
        "| REST API | `api-source` | `connectivity_check.py`; endpoint attributes | [API](api-source.md) |\n",
        encoding="utf-8",
    )

    result = extract_claims(root)

    assert [claim.category for claim in result.claims] == ["type"] * 4
    assert [claim.skill_file for claim in result.claims] == [
        "fixture-skill/reference/source-types.md"
    ] * 4
    assert [claim.quote.split("|", 2)[1].strip() for claim in result.claims] == [
        "CSV",
        "Other local file",
        "Database",
        "REST API",
    ]


def test_fixture_skill_smoke_always_runs(tmp_path: Path) -> None:
    """Exercise the smoke boundary on a hermetic skills root on every host."""

    installed = _fixture_tree(tmp_path)
    result = extract_claims(installed)
    assert result.baseline.skill_files

"""Regression tests for named-pack membership and reference closure checks."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from zipfile import ZipFile


REPO = Path(__file__).resolve().parents[2]
VALIDATOR_PATH = REPO / "scripts" / "validate_skills.py"
spec = importlib.util.spec_from_file_location("skill_validator", VALIDATOR_PATH)
validator = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(validator)

ARCHIVE_VALIDATOR_PATH = REPO / "scripts" / "validate_archives.py"
archive_spec = importlib.util.spec_from_file_location(
    "archive_validator", ARCHIVE_VALIDATOR_PATH
)
archive_validator = importlib.util.module_from_spec(archive_spec)
assert archive_spec.loader is not None
archive_spec.loader.exec_module(archive_validator)


def test_current_named_packs_have_aligned_membership_and_closed_links():
    assert validator.validate_named_skill_set_alignment(REPO) == []
    assert validator.validate_bundle_reference_closure(REPO) == []


def test_bundle_closure_rejects_cross_bundle_relative_links(tmp_path: Path):
    (tmp_path / ".claude-plugin").mkdir()
    (tmp_path / "evals").mkdir()
    (tmp_path / "src" / "desktop-skill").mkdir(parents=True)
    (tmp_path / "src" / "mesh-skill").mkdir(parents=True)
    (tmp_path / "src" / "desktop-skill" / "SKILL.md").write_text(
        "[mesh](../mesh-skill/SKILL.md)\n", encoding="utf-8"
    )
    (tmp_path / "src" / "mesh-skill" / "SKILL.md").write_text(
        "# mesh\n", encoding="utf-8"
    )
    (tmp_path / ".claude-plugin" / "marketplace.json").write_text(
        json.dumps(
            {
                "plugins": [
                    {
                        "name": "nexty-desktop",
                        "source": "./src",
                        "skills": ["./desktop-skill"],
                    },
                    {
                        "name": "nexty-datamesh",
                        "source": "./src",
                        "skills": ["./mesh-skill"],
                    },
                ]
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "evals" / "skill-sets.yaml").write_text(
        """skill_sets:\n  nexty_desktop:\n    skills:\n      - \"src/desktop-skill\"\n  nexty_datamesh:\n    skills:\n      - \"src/mesh-skill\"\n""",
        encoding="utf-8",
    )

    errors = validator.validate_bundle_reference_closure(tmp_path)

    assert len(errors) == 1
    assert "crosses the nexty-desktop bundle" in errors[0]


def test_closure_rejects_relative_links_to_omitted_repository_files(tmp_path: Path):
    """A link escaping a skill must not become an omitted package dependency."""
    skill_dir = tmp_path / "src" / "desktop-skill"
    skill_dir.mkdir(parents=True)
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "foo.md").write_text("# repository-only\n", encoding="utf-8")
    (skill_dir / "SKILL.md").write_text(
        "[repository-only](../../docs/foo.md)\n", encoding="utf-8"
    )
    (tmp_path / ".claude-plugin").mkdir()
    (tmp_path / ".claude-plugin" / "marketplace.json").write_text(
        json.dumps(
            {
                "plugins": [
                    {
                        "name": "nexty-desktop",
                        "source": "./src",
                        "skills": ["./desktop-skill"],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "evals").mkdir()
    (tmp_path / "evals" / "skill-sets.yaml").write_text("skill_sets:\n", encoding="utf-8")

    source_errors = validator.validate_bundle_reference_closure(tmp_path)

    archive = tmp_path / "nexty-desktop.zip"
    with ZipFile(archive, "w") as zip_file:
        zip_file.writestr(
            ".claude-plugin/plugin.json",
            json.dumps({"name": "nexty-desktop", "version": "1.0.0"}),
        )
        zip_file.writestr(
            "skills/desktop-skill/SKILL.md",
            "[repository-only](../../docs/foo.md)\n",
        )

    archive_errors = archive_validator._validate_archive(
        archive, "nexty-desktop", ["desktop-skill"], "1.0.0"
    )

    assert any("outside the source skill pack" in error for error in source_errors)
    assert any("member omitted from the archive" in error for error in archive_errors)

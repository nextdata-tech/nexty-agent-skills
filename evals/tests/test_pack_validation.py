"""Regression tests for named-pack membership and reference closure checks."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path


REPO = Path(__file__).resolve().parents[2]
VALIDATOR_PATH = REPO / "scripts" / "validate_skills.py"
spec = importlib.util.spec_from_file_location("skill_validator", VALIDATOR_PATH)
validator = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(validator)


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

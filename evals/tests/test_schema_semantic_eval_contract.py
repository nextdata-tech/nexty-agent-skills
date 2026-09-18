"""Keep the schema semantic eval aligned with the shipped public DSL."""

from __future__ import annotations

import json
from pathlib import Path


REPO = Path(__file__).resolve().parents[2]
SCENARIO = REPO / "evals" / "public" / "generate-semantic-layer-dp-from-schema"


def test_schema_semantic_eval_grades_public_dsl_not_private_metadata():
    prompt = (SCENARIO / "prompt.md").read_text(encoding="utf-8")
    checks = json.loads((SCENARIO / "checks.json").read_text(encoding="utf-8"))
    check_text = " ".join(item["check"] for item in checks["checks"])
    text = f"{prompt}\n{check_text}"

    assert "__nxd_semantic__" not in text
    assert 'kind": "grain"' not in text
    assert "to_model" not in text
    for required in (
        "primary_key()",
        "dimension(...)",
        "metric_field(metric(...))",
        "join(to=",
        "boolean=True",
    ):
        assert required in text

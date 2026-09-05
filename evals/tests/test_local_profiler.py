"""The local tabular profiler has one owning skill and remains installable."""

from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys


REPO = Path(__file__).resolve().parents[2]
PROFILE = REPO / "src/nxd-build-semantic-data-product/scripts/profile_tabular.py"
OLD_PROFILE = REPO / "src/nxd-analyze-mesh/scripts/profile_tabular.py"


def test_profiler_has_one_semantic_builder_owner() -> None:
    assert PROFILE.is_file()
    assert not OLD_PROFILE.exists()


def test_profiler_profiles_a_local_csv(tmp_path: Path) -> None:
    source = tmp_path / "orders.csv"
    source.write_text("order_id,amount\nA-1,12.5\nA-2,\n", encoding="utf-8")

    result = subprocess.run(
        [sys.executable, str(PROFILE), str(source)],
        check=True,
        capture_output=True,
        text=True,
    )

    profile = json.loads(result.stdout)
    assert profile["format"] == "csv"
    assert profile["columns"]["order_id"]["cardinality"] == 1.0
    assert profile["columns"]["amount"]["nullable"] is True

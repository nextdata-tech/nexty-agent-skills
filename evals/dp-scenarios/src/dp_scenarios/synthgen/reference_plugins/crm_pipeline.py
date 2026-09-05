"""Reference artifact for the route-backed CRM fixture identity."""

from __future__ import annotations

from pathlib import Path

from ..reference import ReferenceGold, register_reference_builder


def _crm_pipeline_gold(data_dir: Path) -> ReferenceGold:
    del data_dir
    return ReferenceGold(files={"crm_pipeline_fixture.json": []})


register_reference_builder("crm_pipeline", _crm_pipeline_gold)


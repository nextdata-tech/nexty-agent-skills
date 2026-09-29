"""Harness-owned source transitions for chained source-drift scenarios."""

from __future__ import annotations

import pytest

from dp_scenarios.mockrest.config import load_config
from dp_scenarios.runner.environment import MockSourceHandle


def test_mock_source_handle_switches_state_on_its_owning_loop() -> None:
    config = load_config(
        {
            "routes": [
                {
                    "path": "/deals",
                    "method": "GET",
                    "state_family": "crm_deals",
                    "initial_state": "v1",
                    "states": {
                        "v1": {"json": [{"id": "DEAL-1"}]},
                        "v2": {"json": [{"id": "DEAL-2"}]},
                    },
                    "pagination": {"page_size": 1},
                }
            ]
        }
    )
    source = MockSourceHandle(config).start()
    try:
        source.set_dataset_state("crm_deals", "v2")
        assert source.snapshot_runtime_state()["current_states"] == {
            "crm_deals": "v2"
        }
        with pytest.raises(ValueError, match="unknown dataset state"):
            source.set_dataset_state("crm_deals", "v3")
        assert source.snapshot_runtime_state()["current_states"] == {
            "crm_deals": "v2"
        }
    finally:
        source.stop()

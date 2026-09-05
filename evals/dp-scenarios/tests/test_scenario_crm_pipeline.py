"""Acceptance tests for the B1 CRM pipeline package."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from aiohttp import ClientSession

from dp_scenarios.mockrest import MockRestServer
from dp_scenarios.runner.environment import PinnedVersions, RunEnvironment
from dp_scenarios.runner.tier import _follow_up_artifact
from dp_scenarios.scenario import load_scenario


ROOT = Path(__file__).parents[1]
SCENARIO = load_scenario(ROOT / "scenarios/crm-pipeline")
MARKER = "crm-pii-sentinel-4e2b7f9c"


def _pins() -> PinnedVersions:
    return PinnedVersions("skills-1", "supervisor-1", "wheel-1", "mock-1", "claims-1")


def _good_target() -> dict[str, object]:
    rows = [
        {"id": "DEAL-2001", "stage": "negotiation"},
        {"id": "DEAL-2002", "stage": "qualification"},
        {"id": "DEAL-2003", "stage": "closed_won"},
        {"id": "DEAL-2004", "stage": "prospecting"},
        {"id": "DEAL-2005", "stage": "closed_lost"},
    ]
    return {
        "pages": [
            {"status": 200, "rows": rows[:2], "next_cursor": "cursor-2"},
            {"status": 200, "rows": rows[2:4], "next_cursor": "cursor-4"},
            {"status": 200, "rows": rows[4:], "next_cursor": None},
        ],
        "transport_trace": [{"status": 401}, {"status": 429}, {"status": 200}],
        "result_rows": [
            {"deal_id": "DEAL-2001", "stage": "negotiation", "amount": 48200, "updated_at": "2024-01-05T10:00:00+00:00"},
            {"deal_id": "DEAL-2002", "stage": "qualification", "amount": 15600, "updated_at": "2024-01-04T16:30:00+00:00"},
            {"deal_id": "DEAL-2003", "stage": "closed_won", "amount": 72300, "updated_at": "2024-01-06T09:15:00+00:00"},
            {"deal_id": "DEAL-2004", "stage": "prospecting", "amount": 9100, "updated_at": "2024-01-02T11:45:00+00:00"},
            {"deal_id": "DEAL-2005", "stage": "closed_lost", "amount": 26400, "updated_at": "2024-01-03T14:20:00+00:00"},
        ],
        "output_contract": {"deal_id": "included", "stage": "included", "amount": "included", "updated_at": "included", "owner": "excluded", "email": "excluded"},
        "surfaces": {"landed": "deal_id,stage,amount,updated_at", "description": "Owner contact details are excluded."},
    }


def test_b1_loads_as_core_with_a_real_mock_route_table() -> None:
    assert SCENARIO.run_order == 7
    assert SCENARIO.tier == "core"
    assert SCENARIO.route_table is not None
    assert SCENARIO.events.planted_card_ids() == {"crm_pipeline_pagination"}


def test_good_pagination_retry_and_redacted_contract_pass() -> None:
    result = SCENARIO.follow_up_check(_good_target())
    assert result["status"] == "examined"
    assert result["passed"]


def test_missing_page_is_not_silently_accepted() -> None:
    target = _good_target()
    target["pages"] = target["pages"][:2]  # type: ignore[index]
    result = SCENARIO.follow_up_check(target)
    assert not result["passed"]
    assert "pagination_rows_disagree_with_route_gold" in result["findings"]


def test_pii_leak_and_unredacted_owner_fail() -> None:
    target = _good_target()
    target["surfaces"] = {"query": MARKER}
    target["output_contract"] = {"owner": "included"}
    result = SCENARIO.follow_up_check(target)
    assert not result["passed"]
    assert "pii_sentinel_leaked:query" in result["findings"]
    assert "output_contract_pii_policy_missing:email" in result["findings"]


def test_not_examined_when_transport_evidence_is_absent() -> None:
    target = _good_target()
    target.pop("transport_trace")
    result = SCENARIO.follow_up_check(target)
    assert result["status"] == "not-examined"
    assert result["findings"] == ["transport_retry_not_examined"]


def test_declared_route_really_exercises_expiry_rate_limit_and_pagination() -> None:
    async def exercise() -> None:
        assert SCENARIO.route_table is not None
        async with MockRestServer(SCENARIO.route_table) as server:
            token = {"Authorization": "Bearer crm-run-token"}
            async with ClientSession() as session:
                response = await session.get(f"{server.data_url}/deals")
                assert response.status == 401
                page = await (await session.get(f"{server.data_url}/deals", headers=token)).json()
                assert len(page["data"]) == 2
                cursor = page["next_cursor"]
                limited = await session.get(
                    f"{server.data_url}/deals?cursor={cursor}", headers=token
                )
                assert limited.status == 429
                refreshed = await session.post(f"{server.data_url}/auth/refresh")
                assert refreshed.status == 200
                second = await (
                    await session.get(f"{server.data_url}/deals?cursor={cursor}", headers=token)
                ).json()
                third = await (
                    await session.get(
                        f"{server.data_url}/deals?cursor={second['next_cursor']}", headers=token
                    )
                ).json()
                source_rows = page["data"] + second["data"] + third["data"]
                assert [item["id"] for item in source_rows] == [
                    "DEAL-2001", "DEAL-2002", "DEAL-2003", "DEAL-2004", "DEAL-2005", "DEAL-2006"
                ]
                assert source_rows[-1]["status"] == "deleted"

    asyncio.run(exercise())


def test_runner_handover_names_auth_without_printing_the_token(tmp_path: Path) -> None:
    with RunEnvironment(SCENARIO, _pins(), root=tmp_path) as environment:
        profile = (environment.workspace_dir / "infra-profile.yaml").read_text(encoding="utf-8")
        assert "credential_env" in profile
        assert "NXD_EVAL_SOURCE_TOKEN" in profile
        assert "crm-run-token" not in profile
        assert environment.agent_environment["NXD_EVAL_SOURCE_TOKEN"] == "crm-run-token"
        contract = (environment.workspace_dir / "scenario-evidence-contract.json").read_text(
            encoding="utf-8"
        )
        assert "evidence/crm_pipeline.json" in contract
        assert MARKER not in contract


def test_declared_evidence_artifact_is_the_follow_up_input(tmp_path: Path) -> None:
    artifact_root = tmp_path / "artifacts"
    path = artifact_root / "evidence" / "crm_pipeline.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(_good_target()), encoding="utf-8")
    assert _follow_up_artifact(SCENARIO, artifact_root) == _good_target()

    path.write_text("not json", encoding="utf-8")
    assert _follow_up_artifact(SCENARIO, artifact_root) is None

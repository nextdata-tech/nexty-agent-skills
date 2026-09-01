"""Tests for typed run identity and cross-machine fixture hashing."""

import os
import shutil
import unicodedata
from pathlib import Path

import pytest

from dp_scenarios.ledger.manifest import Comparability, Manifest, ManifestError, fixture_dir_hash


def make_manifest(**overrides: object) -> Manifest:
    values: dict[str, object] = {
        "agent_model_id": "agent-v1",
        "agent_sampling_params": {"temperature": 0},
        "judge_model_id": "not-applicable",
        "judge_prompt_hash": "not-applicable",
        "skill_pack_version": "skills-1",
        "supervisor_version": "sup-1",
        "nxd_data_product_wheel_version": "wheel-1",
        "fixture_dir_hash": "fixtures-1",
        "mock_api_version": "mock-1",
        "operator_script_hash": "operator-1",
        "turn_budget": 20,
        "grant_fixture_hash": "not-applicable",
        "scenario_id": "grain-trap",
        "tier": "smoke",
        "trial_index": 1,
        "canary_claims_hash": "canary-1",
        "persona_paraphrase_prompt_hash": "not-applicable",
        "judge_calibration_set_hash": "not-applicable",
        "fixture_seed": 7,
        "fixture_base_instant": "2024-01-01T00:00:00+00:00",
        "run_id": "run-1",
    }
    values.update(overrides)
    return Manifest(**values)


def test_manifest_comparability_has_three_outcomes() -> None:
    baseline = make_manifest()

    identical = baseline.comparable_to(make_manifest())
    assert identical.differing_fields == set()
    assert identical.kind is Comparability.IDENTICAL
    assert not hasattr(identical, "differs_in_exactly_one_field")

    one = baseline.comparable_to(make_manifest(agent_model_id="agent-v2"))
    assert one.differing_fields == {"agent_model_id"}
    assert one.kind is Comparability.SINGLE_FIELD

    two = baseline.comparable_to(make_manifest(agent_model_id="agent-v2", turn_budget=21))
    assert two.differing_fields == {"agent_model_id", "turn_budget"}
    assert two.kind is Comparability.MULTI_FIELD


def test_manifest_requires_scenario_tier_and_typed_positive_budget() -> None:
    values = make_manifest().to_dict()
    values.pop("scenario_id")
    with pytest.raises(ManifestError, match="scenario_id"):
        Manifest.from_mapping(values)

    with pytest.raises(ManifestError, match="turn_budget"):
        make_manifest(turn_budget=0)
    with pytest.raises(ManifestError, match="turn_budget"):
        make_manifest(turn_budget=False)
    with pytest.raises(ManifestError, match="trial_index"):
        make_manifest(trial_index=-1)


def test_not_applicable_is_waived_only_for_smoke_fields() -> None:
    make_manifest(judge_model_id="not-applicable")
    with pytest.raises(ManifestError, match="agent_model_id"):
        make_manifest(agent_model_id="not-applicable")


def test_live_manifest_requires_desktop_fields_but_replay_can_waive_them() -> None:
    with pytest.raises(ManifestError, match="supervisor_binary_path"):
        make_manifest(validation_mode="live")

    replay_values = make_manifest().to_dict()
    replay_values.pop("session_root")
    replay = Manifest.from_mapping(replay_values, replay=True)
    assert replay.session_root == "not-applicable"

    with pytest.raises(ManifestError, match="session_root"):
        Manifest.from_mapping(replay_values)


def test_validation_mode_is_persisted_and_used_by_stored_readers() -> None:
    live_values = make_manifest(
        validation_mode="live",
        supervisor_binary_path="/opt/supervisor#sha256:abc",
        session_root="/tmp/session",
        session_config_path="/tmp/session/mcp-config.json",
        session_config_sha256="sha256:config",
        session_trace_path="/tmp/session/mcp-trace.jsonl",
        session_server_result_path="/tmp/session/server-result.json",
    ).to_dict()
    assert live_values["validation_mode"] == "live"
    parsed = Manifest.from_mapping(live_values, replay=None)
    assert parsed.validation_mode == "live"

    live_values.pop("session_root")
    with pytest.raises(ManifestError, match="session_root"):
        Manifest.from_mapping(live_values, replay=None)


def test_stored_pre_mode_live_identity_is_not_implicitly_waived() -> None:
    live_values = make_manifest(
        supervisor_binary_path="/opt/supervisor#sha256:abc",
        session_root="/tmp/session",
        session_config_path="/tmp/session/mcp-config.json",
        session_config_sha256="sha256:config",
        session_trace_path="/tmp/session/mcp-trace.jsonl",
        session_server_result_path="/tmp/session/server-result.json",
    ).to_dict()
    live_values.pop("validation_mode")

    parsed = Manifest.from_mapping(live_values, replay=None)
    assert parsed.validation_mode == "live"

    live_values.pop("session_root")
    with pytest.raises(ManifestError, match="session_root"):
        Manifest.from_mapping(live_values, replay=None)


def test_manifest_rejects_an_unknown_tier() -> None:
    with pytest.raises(ManifestError, match="unknown tier"):
        make_manifest(tier="banana")


def test_fixture_hash_is_stable_across_paths_copies_and_metadata(tmp_path: Path) -> None:
    first = tmp_path / "first"
    first.mkdir()
    (first / "b.txt").write_bytes(b"bravo")
    nested = first / "nested"
    nested.mkdir()
    (nested / "a.bin").write_bytes(b"alpha")
    (first / ".ignored").write_bytes(b"one")
    cache = first / "__pycache__"
    cache.mkdir()
    (cache / "ignored.pyc").write_bytes(b"one")

    second = tmp_path / "second"
    shutil.copytree(first, second)
    assert fixture_dir_hash(first) == fixture_dir_hash(second)
    assert fixture_dir_hash(first) == fixture_dir_hash(first / ".")

    (nested / "a.bin").write_bytes(b"alphA")
    assert fixture_dir_hash(first) != fixture_dir_hash(second)

    empty = first / "empty"
    before_empty = fixture_dir_hash(first)
    empty.mkdir()
    assert fixture_dir_hash(first) != before_empty

    executable = first / "script.sh"
    executable.write_bytes(b"#!/bin/sh\n")
    non_executable = fixture_dir_hash(first)
    executable.chmod(executable.stat().st_mode | 0o100)
    assert fixture_dir_hash(first) != non_executable


def test_fixture_hash_does_not_follow_symlink_and_normalizes_names(tmp_path: Path) -> None:
    root = tmp_path / "links"
    root.mkdir()
    outside = tmp_path / "outside.txt"
    outside.write_bytes(b"outside-v1")
    os.symlink("../outside.txt", root / "external")
    first = fixture_dir_hash(root)
    outside.write_bytes(b"outside-v2")
    assert fixture_dir_hash(root) == first

    os.symlink(outside, root / "absolute")
    with pytest.raises(ManifestError, match="absolute symlink"):
        fixture_dir_hash(root)

    nfc = unicodedata.normalize("NFC", "café.txt")
    nfd = unicodedata.normalize("NFD", "café.txt")
    nfc_root = tmp_path / "nfc"
    nfd_root = tmp_path / "nfd"
    nfc_root.mkdir()
    nfd_root.mkdir()
    (nfc_root / nfc).write_bytes(b"same")
    (nfd_root / nfd).write_bytes(b"same")
    assert fixture_dir_hash(nfc_root) == fixture_dir_hash(nfd_root)


def test_manifest_rejects_missing_and_unknown_fields() -> None:
    values = make_manifest().to_dict()
    values.pop("grant_fixture_hash")
    with pytest.raises(ManifestError, match="grant_fixture_hash"):
        Manifest.from_mapping(values)

    values = make_manifest().to_dict()
    values["unexpected"] = "value"
    with pytest.raises(ManifestError, match="unexpected"):
        Manifest.from_mapping(values)

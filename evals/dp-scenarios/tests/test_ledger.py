"""Behavioural tests for chained, append-only ledger storage."""

import json
from pathlib import Path

import pytest

from dp_scenarios.ledger.manifest import Manifest
from dp_scenarios.ledger.schema import LedgerRow, SchemaError
from dp_scenarios.ledger.store import (
    LedgerError,
    LedgerFormatError,
    LedgerLockError,
    LedgerStore,
    LedgerTamperError,
    read_ledger,
)


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


def make_row(**overrides: object) -> LedgerRow:
    values: dict[str, object] = {
        "run_id": "run-1",
        "scenario_id": "grain-trap",
        "turn": 1,
        "phase": 1,
        "phase_status": "executed",
        "phase_status_reason": None,
        "action_kind": "intake",
        "action": "intake recorded",
        "artifact_ref": None,
        "claim": None,
        "evidence_ref": None,
        "qualification": None,
        "supersedes": None,
        "term": None,
        "fact_key": None,
    }
    values.update(overrides)
    return LedgerRow(**values)


def test_round_trip_append_and_read_materializes_store_identity(tmp_path: Path) -> None:
    path = tmp_path / "run.jsonl"
    manifest = make_manifest()
    row = make_row(
        claim="the product was published",
        evidence_ref="inspect_run.json#publish",
        qualification="strong",
    )

    with LedgerStore.open(path, manifest) as store:
        store.append(row)
        records = store.read()
        assert records[1]["row_id"] == 1
        assert isinstance(records[1]["prev_digest"], str)

    records = read_ledger(path)
    assert len(records) == 2
    assert records[0]["record_type"] == "run_manifest"
    assert records[0]["manifest"] == manifest.to_dict()
    assert row.row_id is None
    assert row.prev_digest is None
    assert records[1]["run_id"] == row.run_id
    assert records[1]["claim"] == row.claim
    assert records[1]["row_id"] == 1
    assert isinstance(records[1]["prev_digest"], str)


def test_open_initializes_an_empty_ledger_before_append(tmp_path: Path) -> None:
    path = tmp_path / "missing.jsonl"
    path.write_text("", encoding="utf-8")
    with LedgerStore.open(path, make_manifest()) as store:
        store.append(make_row())
    assert len(read_ledger(path)) == 2


def test_open_rejects_a_non_manifest_row_zero(tmp_path: Path) -> None:
    path = tmp_path / "wrong-first-row.jsonl"
    path.write_text(json.dumps(make_row().to_dict()) + "\n", encoding="utf-8")
    with pytest.raises(LedgerError, match="row 0"):
        LedgerStore.open(path, make_manifest())


def test_open_refuses_a_changed_existing_manifest(tmp_path: Path) -> None:
    path = tmp_path / "changed-manifest.jsonl"
    with LedgerStore.open(path, make_manifest()) as store:
        store.append(make_row())
    with pytest.raises(LedgerError, match="different row 0 manifest"):
        LedgerStore.open(path, make_manifest(agent_model_id="agent-v2"))


def test_malformed_line_reports_file_and_line(tmp_path: Path) -> None:
    path = tmp_path / "malformed.jsonl"
    with LedgerStore.open(path, make_manifest()) as store:
        store.append(make_row())
    with path.open("ab") as handle:
        handle.write(b"{not-json}\n")

    with pytest.raises(LedgerFormatError, match=r"malformed\.jsonl at line 3"):
        read_ledger(path)


def test_tampering_a_prior_row_is_rejected_before_append_and_bytes_survive(tmp_path: Path) -> None:
    path = tmp_path / "tampered.jsonl"
    with LedgerStore.open(path, make_manifest()) as store:
        store.append(make_row(claim="rows=1000", evidence_ref="inspect#rows", qualification="strong"))
        store.append(make_row(turn=2, phase=2, action_kind="capability_probe"))
    original = path.read_bytes()
    lines = original.splitlines(keepends=True)
    tampered = json.loads(lines[1])
    tampered["claim"] = "rows=9999"
    lines[1] = (json.dumps(tampered, separators=(",", ":")) + "\n").encode()
    path.write_bytes(b"".join(lines))

    with pytest.raises(LedgerTamperError, match=r"line 2.*detected at line 3"):
        LedgerStore.open(path, make_manifest())
    assert path.read_bytes() == b"".join(lines)


def test_deleting_the_row_zero_chain_anchor_is_tampering(tmp_path: Path) -> None:
    path = tmp_path / "missing-row-zero-anchor.jsonl"
    with LedgerStore.open(path, make_manifest()) as store:
        store.append(make_row())

    lines = path.read_bytes().splitlines(keepends=True)
    manifest = json.loads(lines[0])
    del manifest["chain_anchor"]
    lines[0] = (json.dumps(manifest, separators=(",", ":")) + "\n").encode()
    path.write_bytes(b"".join(lines))

    with pytest.raises(LedgerTamperError, match=r"line 1: missing chain anchor"):
        read_ledger(path)


def test_row_zero_chain_anchor_covers_manifest_edits(tmp_path: Path) -> None:
    path = tmp_path / "changed-row-zero.jsonl"
    with LedgerStore.open(path, make_manifest()) as store:
        store.append(make_row())

    lines = path.read_bytes().splitlines(keepends=True)
    manifest = json.loads(lines[0])
    manifest["manifest"]["scenario_id"] = "S7"
    # Keep the old anchor and sidecar: only the manifest bytes are changed.
    lines[0] = (json.dumps(manifest, separators=(",", ":")) + "\n").encode()
    path.write_bytes(b"".join(lines))

    with pytest.raises(LedgerTamperError, match=r"line 1: chain anchor mismatch"):
        read_ledger(path)


def test_a_line_without_a_trailing_newline_is_tampering(tmp_path: Path) -> None:
    path = tmp_path / "missing-newline.jsonl"
    with LedgerStore.open(path, make_manifest()) as store:
        store.append(make_row())

    path.write_bytes(path.read_bytes().removesuffix(b"\n"))

    with pytest.raises(LedgerTamperError, match=r"line 2: line has no newline"):
        read_ledger(path)


def test_read_requires_the_terminal_anchor_sidecar(tmp_path: Path) -> None:
    path = tmp_path / "missing-anchor.jsonl"
    with LedgerStore.open(path, make_manifest()) as store:
        store.append(make_row())
    path.with_name(path.name + ".anchor").unlink()

    with pytest.raises(LedgerTamperError, match="terminal anchor"):
        read_ledger(path)


def test_truncating_history_is_rejected_before_append(tmp_path: Path) -> None:
    path = tmp_path / "truncated.jsonl"
    with LedgerStore.open(path, make_manifest()) as store:
        store.append(make_row())
        store.append(make_row(turn=2, phase=2, action_kind="capability_probe"))
        store.append(make_row(turn=3, phase=3, action_kind="narrowing"))
    lines = path.read_bytes().splitlines(keepends=True)
    path.write_bytes(b"".join(lines[:2]))
    with pytest.raises(LedgerTamperError, match=r"line 2"):
        LedgerStore.open(path, make_manifest())


def test_failed_append_after_external_tamper_preserves_existing_bytes(tmp_path: Path) -> None:
    path = tmp_path / "tampered-while-open.jsonl"
    with LedgerStore.open(path, make_manifest()) as store:
        store.append(make_row())
        store.append(make_row(turn=2, phase=2, action_kind="capability_probe"))
        lines = path.read_bytes().splitlines(keepends=True)
        changed = json.loads(lines[1])
        changed["action"] = "rewritten"
        lines[1] = (json.dumps(changed, separators=(",", ":")) + "\n").encode()
        path.write_bytes(b"".join(lines))
        before = path.read_bytes()
        with pytest.raises(LedgerTamperError):
            store.append(make_row(turn=3, phase=3, action_kind="narrowing"))
        assert path.read_bytes() == before


def test_failed_append_after_external_truncation_preserves_existing_bytes(tmp_path: Path) -> None:
    path = tmp_path / "truncated-while-open.jsonl"
    with LedgerStore.open(path, make_manifest()) as store:
        store.append(make_row())
        store.append(make_row(turn=2, phase=2, action_kind="capability_probe"))
        lines = path.read_bytes().splitlines(keepends=True)
        path.write_bytes(b"".join(lines[:2]))
        before = path.read_bytes()
        with pytest.raises(LedgerTamperError):
            store.append(make_row(turn=3, phase=3, action_kind="narrowing"))
        assert path.read_bytes() == before


def test_row_id_and_chain_fields_are_not_caller_supplied(tmp_path: Path) -> None:
    path = tmp_path / "owned-fields.jsonl"
    with LedgerStore.open(path, make_manifest()) as store:
        with pytest.raises(TypeError):
            LedgerRow(row_id=99)  # type: ignore[call-arg]
        payload = make_row().to_dict()
        payload.pop("row_id")
        payload.pop("prev_digest")
        payload["row_id"] = 99
        with pytest.raises(SchemaError, match="assigned by LedgerStore"):
            store.append(payload)


def test_two_open_handles_cannot_interleave(tmp_path: Path) -> None:
    path = tmp_path / "locked.jsonl"
    first = LedgerStore.open(path, make_manifest())
    try:
        with pytest.raises(LedgerLockError):
            LedgerStore.open(path, make_manifest())
    finally:
        first.close()

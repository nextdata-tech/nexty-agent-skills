from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest

from dp_scenarios.runner.checkpoint import (
    CheckpointError,
    CheckpointIdentity,
    CheckpointState,
    CheckpointStore,
)


def _identity(*, grading_version: str = "g1") -> CheckpointIdentity:
    return CheckpointIdentity.from_groups(
        {
            "run": {"scenario": "crm-pipeline", "run_id": "run-1"},
            "behavior": {"skill_sha": "skill-1", "harness_sha": "harness-1"},
            "substrate": {"supervisor_sha": "supervisor-1", "model": "sonnet"},
            "grading": {"grading_version": grading_version},
        }
    )


def _state(identity: CheckpointIdentity, checkpoint_id: str = "cp-1", *, parent_id: str | None = None, turn: int = 1, status: str = "complete") -> CheckpointState:
    return CheckpointState(
        checkpoint_id=checkpoint_id,
        parent_id=parent_id,
        committed_turn=turn,
        next_turn=turn + 1,
        phase="construction",
        status=status,  # type: ignore[arg-type]
        continuity_mode="native-resume",
        turn_prefix_digest=f"{turn:064x}",
        identity_digest=identity.digest,
    )


def test_identity_hash_is_stable_across_mapping_order() -> None:
    first = _identity()
    second = CheckpointIdentity.from_groups(
        {
            "grading": {"grading_version": "g1"},
            "substrate": {"model": "sonnet", "supervisor_sha": "supervisor-1"},
            "behavior": {"harness_sha": "harness-1", "skill_sha": "skill-1"},
            "run": {"run_id": "run-1", "scenario": "crm-pipeline"},
        }
    )
    assert first.digest == second.digest
    assert first.to_dict()["digest"] == first.digest


def test_native_resume_rejects_strict_identity_mismatch(tmp_path: Path) -> None:
    identity = _identity()
    store = CheckpointStore(tmp_path)
    store.initialize(identity)
    store.commit(_state(identity))

    changed_skill = CheckpointIdentity.from_groups(
        {**identity.groups, "behavior": {"skill_sha": "skill-2", "harness_sha": "harness-1"}}
    )
    decision = store.decide(changed_skill)
    assert decision.action == "reject"
    assert "behavior" in decision.reason


def test_report_only_explicitly_allows_only_grading_change(tmp_path: Path) -> None:
    identity = _identity()
    store = CheckpointStore(tmp_path)
    store.initialize(identity)
    store.commit(_state(identity))

    changed_grading = _identity(grading_version="g2")
    assert store.decide(changed_grading).action == "reject"
    decision = store.decide(changed_grading, mode="report-only")
    assert decision.action == "regrade"
    assert decision.accepted


def test_commit_persists_atomic_pointer_and_journal(tmp_path: Path) -> None:
    identity = _identity()
    store = CheckpointStore(tmp_path)
    store.initialize(identity)
    state = _state(identity)
    store.commit(state)

    pointer = json.loads((tmp_path / "latest.json").read_text())
    journal_lines = (tmp_path / "journal.jsonl").read_text().splitlines()
    assert pointer["checkpoint_id"] == state.checkpoint_id
    assert len(journal_lines) == 1
    entry = json.loads(journal_lines[0])
    assert entry["checkpoint"]["checkpoint_id"] == state.checkpoint_id
    assert store.latest() == state


def test_payload_is_written_before_and_bound_to_a_checkpoint(tmp_path: Path) -> None:
    identity = _identity()
    store = CheckpointStore(tmp_path)
    store.initialize(identity)
    payload_ref, payload_digest = store.write_payload("cp-1", {"turns": 1, "status": "partial"})
    state = replace(_state(identity), payload_ref=payload_ref, payload_digest=payload_digest)
    store.commit(state)

    assert store.read_payload(store.latest()) == {"turns": 1, "status": "partial"}  # type: ignore[arg-type]


def test_payload_secrets_are_rejected_before_checkpoint_commit(tmp_path: Path) -> None:
    identity = _identity()
    store = CheckpointStore(tmp_path)
    store.initialize(identity)
    with pytest.raises(CheckpointError, match="secret-like"):
        store.write_payload("cp-1", {"access_token": "do-not-write"})
    assert not (tmp_path / "checkpoints" / "cp-1.payload.json").exists()


def test_payload_retries_cannot_overwrite_an_existing_checkpoint_payload(tmp_path: Path) -> None:
    identity = _identity()
    store = CheckpointStore(tmp_path)
    store.initialize(identity)
    first = store.write_payload("cp-1", {"turns": 1})
    assert store.write_payload("cp-1", {"turns": 1}) == first
    with pytest.raises(CheckpointError, match="different content"):
        store.write_payload("cp-1", {"turns": 2})


def test_missing_or_corrupt_latest_recovers_from_journal_without_repair(tmp_path: Path) -> None:
    identity = _identity()
    store = CheckpointStore(tmp_path)
    store.initialize(identity)
    state = _state(identity)
    store.commit(state)
    original_journal = (tmp_path / "journal.jsonl").read_bytes()

    (tmp_path / "latest.json").write_text("{not-json", encoding="utf-8")
    assert store.latest() == state
    assert not (tmp_path / "latest.json").read_text(encoding="utf-8").endswith("\n")

    (tmp_path / "latest.json").unlink()
    assert store.latest() == state
    assert (tmp_path / "journal.jsonl").read_bytes() == original_journal


def test_recovery_rejects_a_checkpoint_with_a_missing_prefix_record(tmp_path: Path) -> None:
    identity = _identity()
    store = CheckpointStore(tmp_path)
    store.initialize(identity)
    first = _state(identity, checkpoint_id="cp-1", turn=1)
    second = _state(identity, checkpoint_id="cp-2", parent_id="cp-1", turn=2)
    store.commit(first)
    store.commit(second)
    (tmp_path / "checkpoints" / "cp-1.json").unlink()
    (tmp_path / "latest.json").unlink()

    # Recovery falls back to the newest intact prefix rather than accepting
    # the orphaned tip or mutating the journal/pointer while doing so.
    assert store.latest() == first


def test_incomplete_checkpoint_is_never_resumable(tmp_path: Path) -> None:
    identity = _identity()
    store = CheckpointStore(tmp_path)
    store.initialize(identity)
    incomplete = _state(identity, status="incomplete")
    store.commit(incomplete)

    decision = store.decide(identity)
    assert decision.action == "reject"
    assert decision.checkpoint == incomplete
    assert "incomplete" in decision.reason


def test_handoff_checkpoint_is_not_accepted_as_native_resume(tmp_path: Path) -> None:
    identity = _identity()
    store = CheckpointStore(tmp_path)
    store.initialize(identity)
    handoff = replace(_state(identity), continuity_mode="handoff")
    store.commit(handoff)

    decision = store.decide(identity)
    assert decision.action == "reject"
    assert "handoff" in decision.reason
    assert store.decide(identity, mode="report-only").action == "regrade"


def test_parent_and_prefix_chain_are_enforced(tmp_path: Path) -> None:
    identity = _identity()
    store = CheckpointStore(tmp_path)
    store.initialize(identity)
    first = _state(identity, checkpoint_id="cp-1", turn=1)
    second = _state(identity, checkpoint_id="cp-2", parent_id="cp-1", turn=2)
    store.commit(first)
    store.commit(second)
    assert store.latest() == second

    wrong_parent = _state(identity, checkpoint_id="cp-3", parent_id="not-cp-2", turn=3)
    with pytest.raises(CheckpointError, match="parent"):
        store.commit(wrong_parent)

    skipped_turn = _state(identity, checkpoint_id="cp-4", parent_id="cp-2", turn=4)
    with pytest.raises(CheckpointError, match="immediately"):
        store.commit(skipped_turn)


def test_secret_payload_is_rejected_before_any_file_is_written(tmp_path: Path) -> None:
    with pytest.raises(CheckpointError, match="secret-like"):
        CheckpointIdentity.from_groups(
            {
                "run": {"scenario": "crm-pipeline", "nested": {"api_token": "do-not-write"}},
                "behavior": {"skill_sha": "skill-1"},
                "substrate": {"supervisor_sha": "supervisor-1"},
                "grading": {"grading_version": "g1"},
            }
        )
    assert not list(tmp_path.iterdir())


def test_obvious_secret_value_is_rejected_without_echoing_it() -> None:
    token = "sk-live-do-not-write"
    with pytest.raises(CheckpointError) as error:
        CheckpointIdentity.from_groups(
            {
                "run": {"scenario": "crm-pipeline", "note": token},
                "behavior": {"skill_sha": "skill-1"},
                "substrate": {"supervisor_sha": "supervisor-1"},
                "grading": {"grading_version": "g1"},
            }
        )
    assert token not in str(error.value)

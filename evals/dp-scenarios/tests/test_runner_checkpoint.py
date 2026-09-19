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
    ClaudeSessionIdentity,
    checkpoint_prefix_digest,
    redact_json,
)


def _identity(*, grading_version: str = "g1") -> CheckpointIdentity:
    return CheckpointIdentity.from_groups(
        {
            "run": {
                "scenario": "crm-pipeline",
                "run_id": "run-1",
                "operator_script_hash": "script-1",
            },
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
        native_session=ClaudeSessionIdentity(
            session_id="00000000-0000-4000-8000-000000000001",
            execution_identity_digest=identity.digest,
        ),
    )


def test_identity_hash_is_stable_across_mapping_order() -> None:
    first = _identity()
    second = CheckpointIdentity.from_groups(
        {
            "grading": {"grading_version": "g1"},
            "substrate": {"model": "sonnet", "supervisor_sha": "supervisor-1"},
            "behavior": {"harness_sha": "harness-1", "skill_sha": "skill-1"},
            "run": {
                "run_id": "run-1",
                "scenario": "crm-pipeline",
                "operator_script_hash": "script-1",
            },
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
    decision = store.decide(expected_identity=changed_skill)
    assert decision.action == "reject"
    assert "behavior" in decision.reason


def test_report_only_explicitly_allows_only_grading_change(tmp_path: Path) -> None:
    identity = _identity()
    store = CheckpointStore(tmp_path)
    store.initialize(identity)
    store.commit(_state(identity))

    changed_grading = _identity(grading_version="g2")
    assert store.decide(expected_identity=changed_grading).action == "reject"
    decision = store.decide(expected_identity=changed_grading, mode="report-only")
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
    payload = {"turns": 1, "status": "partial"}
    state = replace(
        _state(identity),
        turn_prefix_digest=checkpoint_prefix_digest(
            payload,
            checkpoint_id="cp-1",
            parent_id=None,
            parent_prefix_digest=None,
            committed_turn=1,
            phase="construction",
            operator_script_hash="script-1",
            identity_digest=identity.digest,
        ),
        payload_ref=payload_ref,
        payload_digest=payload_digest,
    )
    store.commit(state)

    assert store.read_payload(store.latest()) == {"turns": 1, "status": "partial"}  # type: ignore[arg-type]


def test_payload_backed_child_cannot_forge_its_parent_prefix(tmp_path: Path) -> None:
    identity = _identity()
    store = CheckpointStore(tmp_path)
    store.initialize(identity)

    first_payload = {"turns": 1}
    first_ref, first_digest = store.write_payload("cp-1", first_payload)
    first_prefix = checkpoint_prefix_digest(
        first_payload,
        checkpoint_id="cp-1",
        parent_id=None,
        parent_prefix_digest=None,
        committed_turn=1,
        phase="construction",
        operator_script_hash="script-1",
        identity_digest=identity.digest,
    )
    store.commit(
        replace(
            _state(identity),
            turn_prefix_digest=first_prefix,
            payload_ref=first_ref,
            payload_digest=first_digest,
        )
    )

    second_payload = {"turns": 2}
    second_ref, second_digest = store.write_payload("cp-2", second_payload)
    forged_prefix = checkpoint_prefix_digest(
        second_payload,
        checkpoint_id="cp-2",
        parent_id="cp-1",
        parent_prefix_digest="0" * 64,
        committed_turn=2,
        phase="construction",
        operator_script_hash="script-1",
        identity_digest=identity.digest,
    )
    with pytest.raises(CheckpointError, match="prefix digest"):
        store.commit(
            replace(
                _state(identity, checkpoint_id="cp-2", parent_id="cp-1", turn=2),
                turn_prefix_digest=forged_prefix,
                payload_ref=second_ref,
                payload_digest=second_digest,
            )
        )


def test_payload_secrets_are_rejected_before_checkpoint_commit(tmp_path: Path) -> None:
    identity = _identity()
    store = CheckpointStore(tmp_path)
    store.initialize(identity)
    with pytest.raises(CheckpointError, match="secret-like"):
        store.write_payload("cp-1", {"access_token": "do-not-write"})
    assert not (tmp_path / "checkpoints" / "cp-1.payload.json").exists()


def test_report_redaction_preserves_secret_key_shape_without_echoing_values() -> None:
    secrets = {
        "credentials": {"value": "opaque-credential-value"},
        "secrets": {"value": "opaque-secret-value"},
        "tokens": {"value": "opaque-token-value"},
        "api_keys": {"value": "opaque-api-key-value"},
        "passwords": {"value": "opaque-password-value"},
        "bearer_tokens": {"value": "opaque-bearer-token-value"},
        "session_keys": {"value": "opaque-session-key-value"},
        "clientsecret": "opaque-client-secret-value",
        "privatekey": "opaque-private-key-value",
        "secretkey": "opaque-secret-key-value",
        "sessionkey": "opaque-session-key-value-2",
        "accesskey": "opaque-access-key-value",
        "authtoken": "opaque-auth-token-value",
        "bearertoken": "opaque-bearer-token-value",
        "cookie": "cookie-do-not-write",
        "set-cookie": "set-cookie-do-not-write",
        "apikey": "apikey-do-not-write",
        "api_key": "api-key-do-not-write",
        "Authorization": "Bearer authorization-do-not-write",
        "oauth": "oauth-do-not-write",
        "oauthToken": "oauth-token-do-not-write",
        "oauth_key": "oauth-key-do-not-write",
    }
    ordinary = {
        "monkey": "ordinary-monkey-value",
        "turnkey": "ordinary-turnkey-value",
        "handler": "ordinary-handler-value",
    }
    redacted = redact_json(
        {
            **secrets,
            **ordinary,
            "transcript": "request completed",
            "nested": {"status": "ok"},
        }
    )
    assert isinstance(redacted, dict)
    assert set(redacted) == {*secrets, *ordinary, "transcript", "nested"}
    assert all(redacted[key] == "[redacted]" for key in secrets)
    assert all(redacted[key] == value for key, value in ordinary.items())
    assert redacted["nested"] == {"status": "ok"}
    encoded = json.dumps(redacted, sort_keys=True)
    assert all(json.dumps(value, sort_keys=True) not in encoded for value in secrets.values())


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
    handoff = replace(_state(identity), continuity_mode="handoff", native_session=None)
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


def test_first_checkpoint_must_start_at_turn_one(tmp_path: Path) -> None:
    identity = _identity()
    store = CheckpointStore(tmp_path)
    store.initialize(identity)

    with pytest.raises(CheckpointError, match="turn 1"):
        store.commit(_state(identity, turn=0))


def test_prefix_digest_binds_payload_chain_and_script_metadata() -> None:
    identity = _identity()
    payload = {"turns": [], "metadata": {"touched_file_contents_redacted": True}}
    base = checkpoint_prefix_digest(
        payload,
        checkpoint_id="cp-1",
        parent_id=None,
        parent_prefix_digest=None,
        committed_turn=1,
        phase="construction",
        operator_script_hash="script-1",
        identity_digest=identity.digest,
    )
    assert base != checkpoint_prefix_digest(
        payload,
        checkpoint_id="cp-2",
        parent_id="cp-1",
        parent_prefix_digest=base,
        committed_turn=2,
        phase="construction",
        operator_script_hash="script-1",
        identity_digest=identity.digest,
    )
    assert base != checkpoint_prefix_digest(
        payload,
        checkpoint_id="cp-1",
        parent_id=None,
        parent_prefix_digest=None,
        committed_turn=1,
        phase="construction",
        operator_script_hash="script-2",
        identity_digest=identity.digest,
    )


def test_decide_accepts_a_separately_supplied_matching_identity(tmp_path: Path) -> None:
    identity = _identity()
    store = CheckpointStore(tmp_path)
    store.initialize(identity)
    store.commit(_state(identity))

    expected = CheckpointIdentity.from_dict(identity.to_dict())
    decision = store.decide(expected_identity=expected)
    assert decision.action == "resume"


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


def test_semver_identity_values_are_not_mistaken_for_jwts() -> None:
    identity = CheckpointIdentity.from_groups(
        {
            "run": {"scenario": "crm-pipeline"},
            "behavior": {"skill_pack_version": "0.51.3"},
            "substrate": {"supervisor_version": "0.41.196"},
            "grading": {"grading_version": "v2.0.1-beta.1"},
        }
    )
    assert identity.groups["behavior"]["skill_pack_version"] == "0.51.3"


def test_noncredential_handler_keys_are_allowed() -> None:
    identity = CheckpointIdentity.from_groups(
        {
            "run": {"scenario": "crm-pipeline"},
            "behavior": {"handler": "authorized"},
            "substrate": {"supervisor_version": "0.41.196"},
            "grading": {"grading_version": "v2.0.1"},
        }
    )
    assert identity.groups["behavior"]["handler"] == "authorized"


def test_transcript_prose_is_not_mistaken_for_a_jwt() -> None:
    identity = CheckpointIdentity.from_groups(
        {
            "run": {"scenario": "crm-pipeline"},
            "behavior": {"transcript_delta": "Step one. Step two. Done."},
            "substrate": {"supervisor_version": "0.41.196"},
            "grading": {"grading_version": "v2.0.1"},
        }
    )
    assert identity.groups["behavior"]["transcript_delta"] == "Step one. Step two. Done."


def test_native_session_identity_persists_only_uuid_and_execution_digest(tmp_path: Path) -> None:
    identity = _identity()
    store = CheckpointStore(tmp_path)
    store.initialize(identity)
    state = _state(identity)
    store.commit(state)

    persisted = json.loads((store.records_dir / "cp-1.json").read_text(encoding="utf-8"))
    assert persisted["native_session"] == {
        "session_id": "00000000-0000-4000-8000-000000000001",
        "execution_identity_digest": identity.digest,
    }
    assert set(persisted["native_session"]) == {"session_id", "execution_identity_digest"}


def test_native_session_identity_rejects_non_uuid_or_mismatched_execution_digest() -> None:
    with pytest.raises(CheckpointError, match="UUID"):
        ClaudeSessionIdentity("not-a-session", "0" * 64)
    with pytest.raises(CheckpointError, match="execution identity"):
        ClaudeSessionIdentity("00000000-0000-4000-8000-000000000001", "not-a-digest")


def test_native_checkpoint_requires_a_session_identity() -> None:
    identity = _identity()
    with pytest.raises(CheckpointError, match="session identity"):
        CheckpointState(
            checkpoint_id="cp-1",
            parent_id=None,
            committed_turn=1,
            next_turn=2,
            phase="construction",
            status="complete",
            continuity_mode="native-resume",
            turn_prefix_digest="1" * 64,
            identity_digest=identity.digest,
        )

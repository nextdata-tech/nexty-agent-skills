"""The closed vocabulary that separates an external limit from a defect."""

from __future__ import annotations

import pytest

from dp_scenarios.failure_reasons import (
    CHILD_NO_TERMINAL_RESULT,
    CODEX_PROVIDER_ERROR,
    CODEX_PROVIDER_RETRY_PENDING,
    CODEX_ROOT_TURN_NO_TERMINAL_RESULT,
    PROVIDER_SESSION_LIMIT,
    SHARED_RUNTIME_CONTENTION,
    classify_failure_reason,
    first_reason,
)


@pytest.mark.parametrize(
    "text",
    [
        "Claude usage limit reached. Your limit will reset at 3pm.",
        "API Error: 429 rate_limit_error",
        "Your credit balance is too low to access the Anthropic API",
        "you have reached your 5-hour session limit",
    ],
)
def test_provider_ceilings_classify_as_a_session_limit(text: str) -> None:
    assert classify_failure_reason(text) == PROVIDER_SESSION_LIMIT


def test_codex_retry_pending_has_its_own_failure_class() -> None:
    assert (
        classify_failure_reason(
            "codex_provider_retry_pending (variant=rateLimitExceeded)"
        )
        == CODEX_PROVIDER_RETRY_PENDING
    )


@pytest.mark.parametrize(
    "text",
    [
        "sqlite3.OperationalError: database is locked",
        "could not acquire lock on the runtime store",
        "OSError: [Errno 35] Resource temporarily unavailable",
        "OSError: [Errno 48] Address already in use",
    ],
)
def test_contention_on_shared_state_is_named_as_such(text: str) -> None:
    assert classify_failure_reason(text) == SHARED_RUNTIME_CONTENTION


def test_a_provider_limit_outranks_a_lock_message_in_the_same_text() -> None:
    # Both patterns match; the run cannot continue for the provider reason
    # regardless of the lock, so the ceiling is the actionable one.
    assert (
        classify_failure_reason("database is locked", "usage limit reached")
        == PROVIDER_SESSION_LIMIT
    )


def test_ordinary_agent_prose_is_not_classified() -> None:
    assert classify_failure_reason("The build produced 412 rows.") is None
    assert classify_failure_reason("idle_for=429.3s") is None
    assert classify_failure_reason(None, "") is None


def test_first_reason_ignores_blanks_and_unknown_values() -> None:
    assert first_reason((None, "", "not-a-reason", CHILD_NO_TERMINAL_RESULT)) == CHILD_NO_TERMINAL_RESULT
    assert first_reason((None, "made-up")) is None


def test_first_reason_accepts_the_codex_root_turn_timeout_reason() -> None:
    assert first_reason((CODEX_ROOT_TURN_NO_TERMINAL_RESULT,)) == CODEX_ROOT_TURN_NO_TERMINAL_RESULT


def test_first_reason_accepts_terminal_codex_provider_reasons() -> None:
    assert first_reason((CODEX_PROVIDER_ERROR,)) == CODEX_PROVIDER_ERROR

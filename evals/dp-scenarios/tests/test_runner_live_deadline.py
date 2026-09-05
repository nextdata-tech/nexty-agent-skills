"""A live child that never finishes must fail fast, structured, and reaped.

Issue #238: an interrupted live run reached the report as "ungraded" and
nothing else, so a scenario defect and an external provider ceiling were
indistinguishable.  These tests pin the three things that make an incomplete
run actionable -- a bounded deadline, a closed-vocabulary reason, and a dead
child -- and they do it against real subprocesses, because the defect lived in
the process boundary that an in-memory fake does not have.
"""

from __future__ import annotations

import concurrent.futures
import os
import sys
import time

from dp_scenarios.runner.failure_reasons import (
    CHILD_EXITED_EARLY,
    CHILD_NO_TERMINAL_RESULT,
    PROVIDER_SESSION_LIMIT,
    SHARED_RUNTIME_CONTENTION,
)
from dp_scenarios.runner.session import LiveSession


TURN_TIMEOUT = 0.75
# Generous enough that a slow machine does not flake, tight enough that an
# unbounded read still fails the assertion rather than hanging the suite.
BOUND = 20.0


def _silent_child() -> list[str]:
    """A child that accepts the turn and then never answers."""

    return [
        sys.executable,
        "-c",
        "import sys, time\nsys.stdin.readline()\ntime.sleep(600)\n",
    ]


def _announcing_child(message: str) -> list[str]:
    """A child that writes ``message`` to stderr and then never answers."""

    return [
        sys.executable,
        "-c",
        "import sys, time\n"
        "sys.stdin.readline()\n"
        f"sys.stderr.write({message!r})\n"
        "sys.stderr.flush()\n"
        "time.sleep(600)\n",
    ]


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def _run_once(command: list[str]) -> tuple[object, int]:
    session = LiveSession(command, timeout=TURN_TIMEOUT)
    try:
        session.start_fresh_session()
        assert session._process is not None
        pid = session._process.pid
        result = session.send_message("build it")
    finally:
        session.close()
    return result, pid


def test_a_child_with_no_terminal_result_stops_at_the_deadline_and_is_reaped() -> None:
    started = time.monotonic()
    result, pid = _run_once(_silent_child())
    elapsed = time.monotonic() - started

    assert elapsed < BOUND, "the turn deadline did not bound the parent read"
    assert result.turn_timed_out is True
    assert result.environment_wedged is False
    assert result.failure_reason == CHILD_NO_TERMINAL_RESULT
    # The child held stderr open; reading it to EOF is what used to turn a
    # bounded deadline into an unbounded parent hang.
    assert not _alive(pid)


def test_a_provider_ceiling_on_stderr_is_named_instead_of_a_bare_timeout() -> None:
    result, pid = _run_once(
        _announcing_child("Claude usage limit reached. Your limit will reset at 4pm.\n")
    )

    assert result.turn_timed_out is True
    assert result.failure_reason == PROVIDER_SESSION_LIMIT
    assert "usage limit reached" in (result.environment_detail or "")
    assert not _alive(pid)


def test_shared_state_contention_is_named_when_the_child_exits_saying_so() -> None:
    command = [
        sys.executable,
        "-c",
        "import sys\n"
        "sys.stdin.readline()\n"
        "sys.stderr.write('sqlite3.OperationalError: database is locked\\n')\n"
        "sys.stderr.flush()\n"
        "sys.exit(3)\n",
    ]
    result, pid = _run_once(command)

    assert result.turn_timed_out is False
    assert result.environment_wedged is True
    assert result.failure_reason == SHARED_RUNTIME_CONTENTION
    assert not _alive(pid)


def test_a_child_that_exits_silently_is_still_given_a_structured_reason() -> None:
    command = [sys.executable, "-c", "import sys\nsys.stdin.readline()\n"]
    result, _pid = _run_once(command)

    assert result.environment_wedged is True
    assert result.failure_reason == CHILD_EXITED_EARLY


def test_three_concurrent_live_starts_each_finish_bounded_and_leave_no_child() -> None:
    """Three runs starting at once must not serialize into one long wait."""

    started = time.monotonic()
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        futures = [pool.submit(_run_once, _silent_child()) for _ in range(3)]
        outcomes = [future.result(timeout=BOUND) for future in futures]
    elapsed = time.monotonic() - started

    assert elapsed < BOUND
    for result, pid in outcomes:
        assert result.turn_timed_out is True
        assert result.failure_reason == CHILD_NO_TERMINAL_RESULT
        assert not _alive(pid)
    # Distinct children, so the three runs really did overlap rather than
    # reusing one process group.
    assert len({pid for _result, pid in outcomes}) == 3

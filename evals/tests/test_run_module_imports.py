"""``evals/run.py`` must import cleanly, and its stub-setup error must be catchable.

Nothing in this suite imported ``run.py`` before, so a module-level defect in it
was invisible to 537 passing tests and surfaced only as four ERROR'd arms in a
live eval — one that costs real model tokens to discover.

The specific break this pins: a class inserted between
``@contextlib.contextmanager`` and the ``def`` it decorates. Python applies the
decorator to the CLASS, so ``HttpStubSetupError`` becomes a
``_GeneratorContextManager`` factory rather than a type, and the ``except``
clause keyed on it dies with "catching classes that do not inherit from
BaseException is not allowed" — at the moment a scenario errors, which is
exactly when the handler is needed.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

EVALS_DIR = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def run_module():
    sys.path.insert(0, str(EVALS_DIR))
    try:
        import run  # noqa: PLC0415
    finally:
        sys.path.remove(str(EVALS_DIR))
    return run


def test_run_module_imports_cleanly(run_module):
    """A module-level error here ERRORs every arm of every scenario."""
    assert run_module.__name__ == "run"


def test_http_stub_setup_error_is_a_catchable_exception(run_module):
    """It must be a real exception type, not a decorated callable.

    ``issubclass`` alone is not enough: the failure mode is that the name is
    bound to something that is not a class at all, so check that first and then
    actually route a raise through an ``except`` clause the way run.py does.
    """
    exc = run_module.HttpStubSetupError
    assert isinstance(exc, type), (
        f"HttpStubSetupError is {type(exc).__name__}, not a class — a decorator "
        f"above it is being applied to the class instead of a function"
    )
    assert issubclass(exc, BaseException)

    with pytest.raises(exc):
        raise exc("setup fault")


def test_http_stub_server_is_still_a_context_manager(run_module):
    """The decorator must land on the function, not on the class above it.

    Paired with the test above deliberately: moving the class to fix the
    exception is only correct if ``@contextlib.contextmanager`` ends up back on
    ``http_stub_server``. One assertion without the other lets a fix trade one
    break for the other.
    """
    assert hasattr(run_module.http_stub_server, "__wrapped__"), (
        "http_stub_server lost its @contextlib.contextmanager decorator — "
        "`with http_stub_server(...)` would raise AttributeError at runtime"
    )

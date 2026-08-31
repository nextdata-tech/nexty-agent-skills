"""Offline transport boundary for scripted operator tests.

The production session driver is intentionally absent.  A small protocol and
an in-memory fake expose exactly the transcript, tool, file, and environment
observations the engine needs without coupling this package to a live agent.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol, TypeAlias


@dataclass(frozen=True, slots=True)
class Attachment:
    """A file-like object included in an operator message."""

    name: str
    content: bytes
    kind: str = "file"


@dataclass(frozen=True, slots=True)
class OperatorMessage:
    """One message delivered to the agent under test."""

    text: str
    attachments: tuple[Attachment, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.text, str):
            raise TypeError("operator message text must be a string")
        object.__setattr__(self, "attachments", tuple(self.attachments))


@dataclass(frozen=True, slots=True)
class ToolCall:
    """A tool invocation observed in one completed agent turn."""

    name: str
    arguments: object = None
    result: object = None


@dataclass(frozen=True, slots=True)
class TouchedFile:
    """A touched path and the bytes available to the sentinel monitor."""

    path: str | Path
    content: bytes | str | None = None


@dataclass(frozen=True, slots=True)
class TurnResult:
    """The complete offline observation returned by one fake turn.

    ``transcript_delta`` is agent output only; it must not include the operator
    turn or event injections, because monitors scan this field for agent leaks.
    """

    transcript_delta: str | bytes = ""
    agent_message: str | bytes = ""
    tool_calls: tuple[ToolCall, ...] = ()
    tool_results: tuple[object, ...] = ()
    files_touched: tuple[TouchedFile, ...] = ()
    approval_artifact: str | bytes | None = None
    build_failed: bool = False
    build_failure_count: int = 0
    reported: bool = False
    environment_wedged: bool = False
    environment_detail: str | None = None
    session_id: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "tool_calls", tuple(self.tool_calls))
        object.__setattr__(self, "tool_results", tuple(self.tool_results))
        object.__setattr__(self, "files_touched", tuple(self.files_touched))
        if self.build_failure_count < 0:
            raise ValueError("build_failure_count must be non-negative")


class Transport(Protocol):
    """The only session operations the deterministic engine may call."""

    def send_message(self, message: OperatorMessage) -> TurnResult:
        """Send one operator message and wait for the completed turn."""

    def start_fresh_session(self) -> str | None:
        """Discard continuity and start a new session."""

    def resume_session(self, session_id: str | None = None) -> str | None:
        """Resume an existing session when the environment supports it."""


ResponseFactory: TypeAlias = Callable[[OperatorMessage, int], TurnResult]


def _coerce_turn_result(value: TurnResult | Mapping[str, object]) -> TurnResult:
    if isinstance(value, TurnResult):
        return value
    if not isinstance(value, Mapping):
        raise TypeError("fake transport responses must be TurnResult values or mappings")
    allowed = set(TurnResult.__dataclass_fields__)  # type: ignore[attr-defined]
    unknown = set(value) - allowed
    if unknown:
        raise TypeError("fake transport response has unknown field(s): " + ", ".join(sorted(unknown)))
    return TurnResult(**dict(value))  # type: ignore[arg-type]


class InMemoryTransport:
    """Deterministic fake transport with complete message history."""

    def __init__(
        self,
        responses: Sequence[TurnResult | Mapping[str, object]] | ResponseFactory = (),
        *,
        default_response: TurnResult | Mapping[str, object] | None = None,
    ) -> None:
        self._responses = responses
        self._default = _coerce_turn_result(default_response or TurnResult())
        self._index = 0
        self._session_counter = 0
        self._current_session: str | None = None
        self.sent_messages: list[OperatorMessage] = []
        self.started_fresh: list[str] = []
        self.resumed: list[str | None] = []

    @property
    def messages(self) -> tuple[OperatorMessage, ...]:
        """Return the immutable sequence of messages sent to the fake."""

        return tuple(self.sent_messages)

    @property
    def message_texts(self) -> tuple[str, ...]:
        """Return message text for byte-stable sequence assertions."""

        return tuple(message.text for message in self.sent_messages)

    def send_message(self, message: OperatorMessage | str) -> TurnResult:
        """Record a message and return the next fixed observation."""

        if isinstance(message, str):
            message = OperatorMessage(message)
        if not isinstance(message, OperatorMessage):
            raise TypeError("message must be an OperatorMessage or string")
        self.sent_messages.append(message)
        if callable(self._responses):
            return self._responses(message, len(self.sent_messages))
        if self._index < len(self._responses):
            response = self._responses[self._index]
            self._index += 1
            return _coerce_turn_result(response)
        return self._default

    send = send_message

    def start_fresh_session(self) -> str:
        """Start a new fake session and intentionally discard continuity."""

        self._session_counter += 1
        self._current_session = f"session-{self._session_counter}"
        self.started_fresh.append(self._current_session)
        return self._current_session

    start_fresh = start_fresh_session

    def resume_session(self, session_id: str | None = None) -> str | None:
        """Record a resume request without fabricating persisted state."""

        self.resumed.append(session_id)
        self._current_session = session_id
        return session_id

    resume = resume_session


FakeTransport = InMemoryTransport


__all__ = [
    "Attachment",
    "InMemoryTransport",
    "FakeTransport",
    "OperatorMessage",
    "ToolCall",
    "Transport",
    "TouchedFile",
    "TurnResult",
]

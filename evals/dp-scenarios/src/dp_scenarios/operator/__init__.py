"""Deterministic scripted operators for offline data-product evaluations.

The package keeps operator behaviour in validated fixture data and keeps all
state transitions in the engine.  This separation makes repeated trials
byte-stable while allowing persona cards to carry realistic pressure.
"""

from .answer_sheet import (
    AnswerSheet,
    AnswerSheetError,
    DecisionAnswer,
    GroundTruthFact,
    answer_sheet_from_mapping,
    load_answer_sheet,
)
from .appender import (
    AppenderError,
    StaticSupervisorRecordReader,
    SupervisorRecordReader,
    TurnEvidence,
    append_supervisor_facts,
    append_turn_row,
)
from .engine import (
    Engine,
    Outcome,
    OperatorEngine,
    OperatorScript,
    ScriptTurn,
    RunState,
    RunOutcome,
    RunResult,
    TerminalState,
    operator_script_hash,
)
from .events import EventCard, EventInjection, EventSchedule, EventType, event_from_mapping, load_event_cards
from .generated import GeneratedOperator, OperatorProvider, OperatorRender, OperatorView
from .driver import (
    DriverBeat,
    DriverOperator,
    DriverProvider,
    DriverRender,
    DriverViolation,
    DriverView,
    beat_violation,
    leading_violation,
    repeat_violation,
)
from .matcher import Category, MatchResult, MatcherBank, MatcherError
from .persona import PersonaCard, PersonaError, load_persona, persona_from_mapping
from .transport import (
    Attachment,
    FakeTransport,
    InMemoryTransport,
    OperatorMessage,
    ToolCall,
    TouchedFile,
    TurnResult,
    Transport,
)

__all__ = [
    "AnswerSheet",
    "AnswerSheetError",
    "answer_sheet_from_mapping",
    "AppenderError",
    "Attachment",
    "Category",
    "DecisionAnswer",
    "GroundTruthFact",
    "EventCard",
    "EventInjection",
    "EventSchedule",
    "EventType",
    "GeneratedOperator",
    "DriverBeat",
    "DriverOperator",
    "DriverProvider",
    "DriverRender",
    "DriverViolation",
    "DriverView",
    "beat_violation",
    "event_from_mapping",
    "Engine",
    "Outcome",
    "FakeTransport",
    "InMemoryTransport",
    "MatchResult",
    "MatcherBank",
    "MatcherError",
    "OperatorEngine",
    "OperatorMessage",
    "OperatorProvider",
    "OperatorRender",
    "OperatorScript",
    "OperatorView",
    "leading_violation",
    "ScriptTurn",
    "PersonaCard",
    "PersonaError",
    "persona_from_mapping",
    "RunOutcome",
    "RunState",
    "RunResult",
    "TerminalState",
    "StaticSupervisorRecordReader",
    "SupervisorRecordReader",
    "ToolCall",
    "TouchedFile",
    "Transport",
    "TurnEvidence",
    "TurnResult",
    "append_supervisor_facts",
    "append_turn_row",
    "load_answer_sheet",
    "load_event_cards",
    "load_persona",
    "operator_script_hash",
    "repeat_violation",
]

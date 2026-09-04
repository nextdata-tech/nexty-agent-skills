"""Human-inspectable rendering of one epoch evidence bundle.

The harness already writes everything a reader needs to reconstruct a run, but
it writes it as JSON split across two artifacts whose turn records mean
different things.  Debugging a live failure therefore meant hand-decoding
`session-replay.json` next to `operator-observations.json` and holding the
correspondence between them in your head.  This module renders the pair as one
readable conversation so the instrument is the file, not the reader.

Two properties are load-bearing.

**Attribution is off by one.**  `operator_matched_rule_id` recorded on turn N is
the classification of the *agent's* turn-N message; the operator reply it
selects is spoken on turn N+1.  Turn 1's operator message is the scenario's
fixed opening and was selected by nothing.  Rendering turn N's operator line
with turn N's own rule id would therefore mis-attribute every line in the file
and quietly libel the matcher, so the renderer attributes an operator line to
turn N-1's classification and labels turn 1 as the fixed opening.

**Degradation is visible.**  The harness is fail-closed, and a renderer that
silently drops a malformed turn is worse than one that crashes: the reader
concludes the turn never happened.  Every unreadable input, missing artifact and
malformed record is rendered as a ``!!`` marker in place, and the turn is still
emitted.

The rendering is a pure function of the bundle directory (plus an explicitly
passed report), so it runs retroactively against bundles already on disk.  Gold
row-sets, ledger bytes and oracle files are never read.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

__all__ = [
    "OPENING_ATTRIBUTION",
    "render_epoch_conversation",
]

#: Marker prefix for every degraded / unreadable input.  One token so a reader
#: (or a grep) can find every place the rendering is not the whole truth.
MARKER = "!!"

#: Label column width: ``"OPERATOR> "`` is the widest speaker label, and
#: continuation lines align under it.
_LABEL_WIDTH = 10

#: What turn 1's operator line is attributed to.  Not a rule id: nothing
#: classified it.
OPENING_ATTRIBUTION = "fixed scenario opening (selected by nothing)"

#: Tool arguments and results are elided by default; ``verbose=True`` includes
#: them, capped so one enormous Bash result cannot bury the conversation.
_VERBOSE_VALUE_CAP = 1200

# Only these files are ever opened, and only relative to the bundle directory.
# Gold row-sets (``oracle/``), the ledger and the fixture data are deliberately
# absent: a conversation renderer has no business reading the answer key.
_SESSION_REPLAY = ("artifacts", "session-replay.json")
_OBSERVATIONS = ("artifacts", "operator-observations.json")
_MANIFEST = ("manifest.json",)
_QUALIFICATION = ("qualification.json",)


# --------------------------------------------------------------------------
# loading
# --------------------------------------------------------------------------


def _read_json(bundle_dir: Path, parts: Sequence[str]) -> tuple[Any, str | None]:
    """Read one bundle-relative JSON file.

    Returns ``(value, error)``.  Never raises: an unreadable artifact is a
    thing to render, not a thing to die on.
    """

    path = bundle_dir.joinpath(*parts)
    try:
        raw = path.read_text(encoding="utf-8", errors="replace")
    except FileNotFoundError:
        return None, f"{'/'.join(parts)} is missing"
    except OSError as exc:  # unreadable, a directory, a broken link
        return None, f"{'/'.join(parts)} could not be read ({exc.__class__.__name__})"
    try:
        return json.loads(raw), None
    except ValueError as exc:
        return None, f"{'/'.join(parts)} is not valid JSON ({exc})"


def _mapping(value: Any) -> Mapping[str, Any]:
    """Coerce to a mapping without raising; non-mappings become empty."""

    return value if isinstance(value, Mapping) else {}


def _sequence(value: Any) -> list[Any]:
    """Coerce to a list without raising; strings and mappings are not sequences here."""

    if isinstance(value, (str, bytes, Mapping)):
        return []
    return list(value) if isinstance(value, Sequence) else []


def _text(value: Any) -> str | None:
    """Decode a persisted prose value, tolerating bytes and JSON nulls."""

    if value is None:
        return None
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _resolve_report(report: Any) -> tuple[Mapping[str, Any] | None, str | None]:
    """Accept a parsed report, a path to one, or nothing."""

    if report is None:
        return None, None
    if isinstance(report, Mapping):
        return report, None
    if isinstance(report, (str, Path)):
        path = Path(report)
        try:
            raw = path.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            return None, f"report {path} could not be read ({exc.__class__.__name__})"
        try:
            parsed = json.loads(raw)
        except ValueError as exc:
            return None, f"report {path} is not valid JSON ({exc})"
        if not isinstance(parsed, Mapping):
            return None, f"report {path} is not a JSON object"
        return parsed, None
    return None, f"report of unsupported type {type(report).__name__}"


def _report_entry(
    report: Mapping[str, Any] | None,
    scenario_id: str | None,
    epoch: int | None,
) -> Mapping[str, Any] | None:
    """Find the (scenario, epoch) run entry inside a tier-level report.

    The report is tier-level, not per-epoch, so the entry may legitimately be
    absent (a report for a different tier, a truncated report, no report at
    all).  Absence is reported by the caller, never faked.
    """

    if report is None:
        return None
    for scenario in _sequence(report.get("scenarios")):
        entry = _mapping(scenario)
        if scenario_id is not None and entry.get("scenario_id") != scenario_id:
            continue
        for run in _sequence(entry.get("runs")):
            run_map = _mapping(run)
            if epoch is None or run_map.get("epoch") == epoch:
                return run_map
    return None


# --------------------------------------------------------------------------
# formatting helpers
# --------------------------------------------------------------------------


def _indent() -> str:
    return " " * _LABEL_WIDTH


def _speaker(label: str, body: str | None, *, missing: str) -> list[str]:
    """Render one speaker turn: label on the first line, aligned continuations.

    Prose is never truncated — inspecting it is the whole point of the file.
    """

    head = f"{label}>".ljust(_LABEL_WIDTH)
    if body is None:
        return [f"{head}{MARKER} {missing}"]
    lines = body.split("\n") if body else [""]
    out = [f"{head}{lines[0]}"]
    out.extend(f"{_indent()}{line}" if line else "" for line in lines[1:])
    return out


def _note(text: str) -> str:
    return f"{_indent()}{text}"


def _flag(value: Any) -> str:
    """Render a tri-state flag without collapsing ``None`` into ``False``."""

    if value is None:
        return "unknown"
    return "yes" if value else "no"


def _compact(value: Any) -> str:
    """One-line JSON for a tool argument or result, capped for verbose output."""

    if isinstance(value, bytes):
        value = value.decode("utf-8", errors="replace")
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, sort_keys=True)
    text = text.replace("\n", "\\n")
    if len(text) > _VERBOSE_VALUE_CAP:
        return f"{text[:_VERBOSE_VALUE_CAP]}… ({len(text) - _VERBOSE_VALUE_CAP} more chars elided)"
    return text


def _tool_summary(calls: Sequence[Any]) -> str:
    """``name(xN)`` in first-call order, so a reader sees shape not volume."""

    order: list[str] = []
    counts: dict[str, int] = {}
    for call in calls:
        name = _mapping(call).get("name")
        label = name if isinstance(name, str) and name else f"{MARKER} unnamed-tool"
        if label not in counts:
            order.append(label)
            counts[label] = 0
        counts[label] += 1
    return ", ".join(f"{name}(x{counts[name]})" if counts[name] > 1 else name for name in order)


# --------------------------------------------------------------------------
# turn model
# --------------------------------------------------------------------------


class _Turn:
    """One turn assembled from the replay and observation records.

    The two artifacts are zipped positionally because that is how the harness
    writes them; a length disagreement is surfaced rather than resolved.
    """

    def __init__(self, index: int, replay: Any, observation: Any) -> None:
        self.index = index
        self.problems: list[str] = []

        if replay is None:
            self.replay: Mapping[str, Any] = {}
            self.problems.append("no session-replay record for this turn")
        elif isinstance(replay, Mapping):
            self.replay = replay
        else:
            self.replay = {}
            self.problems.append(
                f"malformed session-replay record ({type(replay).__name__}, expected object)"
            )

        if observation is None:
            self.observation: Mapping[str, Any] = {}
            self.problems.append("no operator-observations record for this turn")
        elif isinstance(observation, Mapping):
            self.observation = observation
        else:
            self.observation = {}
            self.problems.append(
                f"malformed operator-observations record ({type(observation).__name__}, expected object)"
            )

        self.result = _mapping(self.replay.get("result"))

    @property
    def phase(self) -> Any:
        return self.observation.get("phase")

    @property
    def operator_text(self) -> str | None:
        message = self.replay.get("operator_message")
        if not isinstance(message, Mapping):
            return None
        return _text(message.get("text"))

    @property
    def attachments(self) -> list[Any]:
        message = self.replay.get("operator_message")
        return _sequence(_mapping(message).get("attachments"))

    @property
    def agent_text(self) -> str | None:
        # The observation copy is the fallback: if the replay record is gone,
        # the agent's words may still be recoverable from the other artifact.
        return _text(self.result.get("agent_message")) or _text(self.observation.get("agent_message"))

    @property
    def tool_calls(self) -> list[Any]:
        calls = _sequence(self.result.get("tool_calls"))
        return calls or _sequence(self.observation.get("tool_calls"))

    @property
    def rule_id(self) -> Any:
        return self.observation.get("operator_matched_rule_id")

    @property
    def matched(self) -> Any:
        return self.observation.get("operator_matched")

    @property
    def ground_truth(self) -> Any:
        return self.observation.get("operator_answered_from_ground_truth")

    @property
    def repeat_suppressed(self) -> Any:
        return self.observation.get("operator_repeat_suppressed")

    @property
    def has_classification(self) -> bool:
        return bool(self.observation)

    @property
    def files_touched(self) -> list[str]:
        raw = _sequence(self.result.get("files_touched")) or _sequence(
            self.observation.get("files_touched")
        )
        paths: list[str] = []
        for entry in raw:
            if isinstance(entry, Mapping):
                # File *contents* are never rendered: they are bulk bytes, and
                # on some scenarios they are the landed data itself.
                path = entry.get("path")
                paths.append(_text(path) or f"{MARKER} unnamed file")
            else:
                paths.append(_text(entry) or f"{MARKER} unnamed file")
        return paths


def _classification_note(turn: _Turn | None) -> str:
    """Describe the classification that selected the *next* operator line."""

    if turn is None or not turn.has_classification:
        return f"{MARKER} classification unavailable"
    rule = turn.rule_id
    rule_text = rule if isinstance(rule, str) and rule else f"{MARKER} no rule id recorded"
    note = (
        f"rule {rule_text} | matched={_flag(turn.matched)} | "
        f"from-ground-truth={_flag(turn.ground_truth)}"
    )
    # Only rendered when the fact was actually withheld. Without it a reader
    # sees a ``ground_truth.*`` rule reported as ``from-ground-truth=no`` and
    # has no way to tell that the engine chose not to re-serve an answer it
    # had already sent. Runs with no re-serve render exactly as before.
    if turn.repeat_suppressed:
        note += " | repeat-suppressed=yes"
    return note


# --------------------------------------------------------------------------
# sections
# --------------------------------------------------------------------------


def _header(
    scenario_id: str | None,
    epoch: int | None,
    entry: Mapping[str, Any] | None,
    observations: Mapping[str, Any],
    qualification: Mapping[str, Any],
    notes: Sequence[str],
) -> list[str]:
    title_scenario = scenario_id or f"{MARKER} unknown scenario"
    title_epoch = epoch if epoch is not None else f"{MARKER} unknown"
    lines = [f"# {title_scenario} — epoch {title_epoch}", ""]

    score = _mapping(_mapping(entry).get("score"))
    if entry is None:
        verdict = f"{MARKER} no report entry"
        total = "n/a"
    else:
        verdict = _text(score.get("state")) or f"{MARKER} absent"
        total = _text(score.get("total")) or f"{MARKER} absent"
    stop = (
        _text(_mapping(entry).get("stop_condition"))
        or _text(observations.get("terminal_state"))
        or f"{MARKER} absent"
    )
    lines.append(f"verdict: {verdict} | stop: {stop} | total: {total}")

    disposition = _text(qualification.get("disposition")) or f"{MARKER} absent"
    replay_status = _text(qualification.get("replay_status")) or f"{MARKER} absent"
    reasons = ", ".join(str(reason) for reason in _sequence(qualification.get("reasons"))) or "none"
    lines.append(
        f"qualification: {disposition} | replay: {replay_status} | reasons: {reasons}"
    )

    lines.append(
        "operator: off-script turns={off} | ground-truth answers={gt} | tool calls={tools}"
        " | mode={mode} | leading-rejected={leading} | obstacle-rejected={obstacle}"
        " | repeat-rejected={repeat} | beat-substituted={beat}".format(
            off=_text(observations.get("operator_unmatched_turn_count")) or "?",
            gt=_text(observations.get("operator_ground_truth_turn_count")) or "?",
            tools=_text(observations.get("tool_call_count")) or "?",
            # Older bundles predate the driver: every driver field is read
            # with ``.get`` so a pre-driver observations file still renders.
            mode=observations.get("operator_mode", "scripted"),
            leading=observations.get("driver_leading_rejected_count", 0),
            obstacle=observations.get("driver_obstacle_rejected_count", 0),
            repeat=observations.get("driver_repeat_rejected_count", 0),
            beat=observations.get("driver_beat_substituted_count", 0),
        )
    )
    for note in notes:
        lines.append(f"{MARKER} {note}")
    return lines


def _gates_section(entry: Mapping[str, Any] | None) -> list[str]:
    lines = ["", "## Gates"]
    if entry is None:
        lines.append(f"{MARKER} no report entry for this epoch — gates unavailable")
        return lines
    score = _mapping(entry.get("score"))
    gates = _mapping(score.get("gates"))
    if not gates:
        lines.append(f"{MARKER} report entry carries no gates")
    for name in sorted(gates):
        gate = _mapping(gates[name])
        status = "PASS" if gate.get("passed") else "FAIL"
        marks = []
        if gate.get("required"):
            marks.append("required")
        if not gate.get("examined"):
            marks.append("not-examined")
        if gate.get("ungraded"):
            marks.append("ungraded")
        codes = ", ".join(str(code) for code in _sequence(gate.get("codes")))
        suffix = f"  [{' '.join(marks)}]" if marks else ""
        lines.append(f"{name.ljust(14)}{status}{suffix}  {codes}".rstrip())
    hard = _mapping(score.get("hard_gate_flags"))
    if hard:
        rendered = " ".join(f"{key}={hard[key]}" for key in sorted(hard))
        lines.append(f"hard gates: {rendered}")
    return lines


def _run_state_section(
    entry: Mapping[str, Any] | None, observations: Mapping[str, Any]
) -> list[str]:
    def listing(*values: Any) -> str:
        for value in values:
            items = _sequence(value)
            if items:
                return ", ".join(str(item) for item in items)
        return "(none)"

    lines = ["", "## Run state"]
    lines.append(f"terminal state: {_text(observations.get('terminal_state')) or MARKER + ' absent'}")
    lines.append(f"fired events:   {listing(observations.get('fired_event_ids'))}")
    lines.append(f"fired plants:   {listing(observations.get('fired_plant_ids'))}")
    lines.append(
        "ungraded:       "
        + listing(
            observations.get("ungraded_criteria"),
            _mapping(entry).get("ungraded_criteria"),
        )
    )
    lines.append(
        "failure modes:  "
        + listing(observations.get("failure_modes"), _mapping(entry).get("failure_modes"))
    )
    return lines


def _turn_section(turn: _Turn, previous: _Turn | None, verbose: bool) -> list[str]:
    phase = turn.phase
    phase_text = f"phase {phase}" if phase is not None else f"{MARKER} phase unknown"
    lines = ["", f"## Turn {turn.index}  ({phase_text})"]
    for problem in turn.problems:
        lines.append(f"{MARKER} {problem}")

    lines.extend(
        _speaker("OPERATOR", turn.operator_text, missing="operator message unavailable")
    )
    if turn.index == 1:
        lines.append(_note(f"[{OPENING_ATTRIBUTION}]"))
    else:
        # The off-by-one: this line was chosen by the *previous* turn's
        # classification of the agent, not by this turn's.
        lines.append(
            _note(f"[selected by turn {turn.index - 1}: {_classification_note(previous)}]")
        )
    attachments = turn.attachments
    if attachments:
        lines.append(_note(f"attachments: {len(attachments)}"))

    lines.extend(_speaker("AGENT", turn.agent_text, missing="agent message unavailable"))
    lines.append(_note(f"[this reply classified as: {_classification_note(turn)}]"))

    calls = turn.tool_calls
    if calls:
        lines.append(_note(f"tools: {_tool_summary(calls)}"))
        if verbose:
            for position, call in enumerate(calls, 1):
                call_map = _mapping(call)
                name = _text(call_map.get("name")) or f"{MARKER} unnamed-tool"
                lines.append(_note(f"  {position}. {name}"))
                lines.append(_note(f"     args: {_compact(call_map.get('arguments'))}"))
                lines.append(_note(f"     result: {_compact(call_map.get('result'))}"))
    else:
        lines.append(_note("tools: none"))

    files = turn.files_touched
    if files:
        lines.append(_note(f"files touched: {', '.join(files)}"))
    return lines


# --------------------------------------------------------------------------
# entry point
# --------------------------------------------------------------------------


def render_epoch_conversation(
    bundle_dir: str | Path,
    *,
    report: Any = None,
    verbose: bool = False,
) -> str:
    """Render one epoch evidence bundle as a readable conversation.

    ``bundle_dir`` is an ``evidence/<scenario>/epoch-<n>/`` directory.  ``report``
    is the optional tier-level ``report.json`` (a path or an already-parsed
    mapping); the matching ``(scenario_id, epoch)`` run entry supplies the
    verdict and gates.  A missing report, a missing entry, and malformed
    artifacts all degrade to visible ``!!`` markers rather than an exception.

    ``verbose`` additionally includes tool arguments and results, which are
    elided by default.
    """

    bundle = Path(bundle_dir)
    notes: list[str] = []

    replay_raw, replay_error = _read_json(bundle, _SESSION_REPLAY)
    if replay_error:
        notes.append(replay_error)
    observations_raw, observations_error = _read_json(bundle, _OBSERVATIONS)
    if observations_error:
        notes.append(observations_error)
    manifest_raw, manifest_error = _read_json(bundle, _MANIFEST)
    if manifest_error:
        notes.append(manifest_error)
    qualification_raw, qualification_error = _read_json(bundle, _QUALIFICATION)
    if qualification_error:
        notes.append(qualification_error)

    replay = _mapping(replay_raw)
    observations = _mapping(observations_raw)
    manifest = _mapping(manifest_raw) or _mapping(replay.get("manifest"))
    qualification = _mapping(qualification_raw)

    scenario_id = _text(manifest.get("scenario_id"))
    if scenario_id is None and bundle.parent.name:
        scenario_id = bundle.parent.name
    epoch = _epoch_from_dir(bundle)

    report_map, report_error = _resolve_report(report)
    if report_error:
        notes.append(report_error)
    entry = _report_entry(report_map, scenario_id, epoch)
    if report_map is not None and entry is None:
        notes.append(
            f"report has no entry for scenario {scenario_id!r} epoch {epoch!r} — "
            "verdict and gates unavailable"
        )
    if report is None:
        notes.append("no report supplied — verdict and gates unavailable")

    replay_turns = _sequence(replay.get("turns"))
    observation_turns = _sequence(observations.get("turns"))
    count = max(len(replay_turns), len(observation_turns))
    if replay_turns and observation_turns and len(replay_turns) != len(observation_turns):
        notes.append(
            f"turn count disagreement: session-replay has {len(replay_turns)}, "
            f"operator-observations has {len(observation_turns)} — rendering the union"
        )

    lines = _header(scenario_id, epoch, entry, observations, qualification, notes)
    lines.extend(_gates_section(entry))
    lines.extend(_run_state_section(entry, observations))
    lines.append("")
    lines.append("## Conversation")
    if count == 0:
        lines.append(f"{MARKER} no turns recorded in this bundle")

    turns = [
        _Turn(
            index,
            replay_turns[index - 1] if index <= len(replay_turns) else None,
            observation_turns[index - 1] if index <= len(observation_turns) else None,
        )
        for index in range(1, count + 1)
    ]
    for position, turn in enumerate(turns):
        lines.extend(_turn_section(turn, turns[position - 1] if position else None, verbose))

    return "\n".join(lines).rstrip() + "\n"


def _epoch_from_dir(bundle: Path) -> int | None:
    name = bundle.name
    prefix = "epoch-"
    if name.startswith(prefix):
        try:
            return int(name[len(prefix) :])
        except ValueError:
            return None
    return None

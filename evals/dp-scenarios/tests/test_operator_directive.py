"""The operator's job on a turn where it has nothing declared to say.

Before these, every such turn arrived at the driver as a persona stock
sentence with the prompt's instruction to convey it. A live 15-turn run spent
eight turns refusing as a result -- including turns where the agent had asked
for nothing at all -- and the agent stalled, made a third of the tool calls of
comparable runs, and never built the product.

The fix is a composition, not a bigger fact bank: the scenario owns what a gap
*means* here (``gap_stance``), the persona owns the tactic for handing one back
(``stance_when_unknown``), and the engine resolves the pair into a
``directive``. These tests pin the composition and the two properties it
exists to protect -- that a stock line is never handed over as substance, and
that a turn nobody asked anything on transmits the author's own script.
"""

from __future__ import annotations

import pytest

from dp_scenarios.operator.answer_sheet import (
    DEFAULT_GAP_STANCE,
    GAP_STANCES,
    AnswerSheetError,
    answer_sheet_from_mapping,
)
from dp_scenarios.operator.driver import DriverView
from dp_scenarios.operator.matcher import (
    Category,
    MatchResult,
    asks_for_a_choice,
    solicits_operator,
)
from dp_scenarios.operator.persona import (
    STANCE_WHEN_UNKNOWN,
    PersonaError,
    load_persona,
)
from dp_scenarios.operator.transport import TurnResult

from test_operator_engine_driver import (  # type: ignore[import-not-found]
    ROOT,
    InMemoryTransport,
    OperatorEngine,
    driver,
    make_script,
)


# --- the solicitation predicate -------------------------------------------

# Every string here is from the live run that motivated the change. The four
# "asked nothing" cases each selected a refusal that then became the driver's
# mandate for the turn.
@pytest.mark.parametrize(
    "message",
    [
        "No action needed from you -- I'll ping you when there's something to look at or approve.",
        # The live turn-8 message. "need your call" promises a *future* ask;
        # reading it as a present one drew a refusal for a decision nobody
        # had requested.
        "I'll surface it if and when something does need your call.",
        # A pasted request path carries a question mark and asks nothing.
        "I fetched /deals?limit=5 and got 200 back.",
        # "confirm" in the agent's own report. Bare confirm-the/that turned a
        # finished-build report into "I don't know, look for yourself".
        "I can confirm that the build finished cleanly. Serving it now.",
        "Self-check passed; I confirm the row counts match. Moving on.",
        "I'd like your patience here -- the transform is slow.",
        "Blueprint: approved. Building it now.",
        "Done. I'll keep going.",
        "I've recorded the decision and will proceed.",
    ],
)
def test_a_status_update_asks_the_operator_for_nothing(message: str) -> None:
    assert solicits_operator(message) is False


@pytest.mark.parametrize(
    "message",
    [
        "Which path should I take -- proxy the field or drop it?",
        "Is there anything else you'd like me to look at?",
        "Please approve the blueprint before I build.",
        "Let me know whether that works for you.",
        "Can you tell me what counts as an active deal?",
        "Shall I proceed with the narrower version?",
        # The verbatim live turn-14 ask: an imperative with no question mark
        # and no interrogative opener. Dropping it yielded a room turn and the
        # agent never got an answer it had directly requested.
        "Tell me a name, role, team, or channel. Or point me at a system that has it.",
        "Can you confirm the grain before I build?",
        "I'd like your go-ahead on the blueprint.",
        "I need a decision from you before I go further.",
    ],
)
def test_a_real_ask_is_recognised(message: str) -> None:
    assert solicits_operator(message) is True


def test_the_approval_flag_and_the_solicitation_flag_are_independent() -> None:
    """The narrow predicate must not be wired to the graded approval flag.

    ``approval_requested`` feeds ledger rows, so it deliberately fires on the
    bare approval vocabulary wherever it appears. Collapsing the two would
    move grading, which is why ``solicits_operator`` is a separate signal.
    """

    passing_mention = "I'll ping you when there's something to approve."
    from dp_scenarios.operator.matcher import APPROVAL_REQUEST_PATTERN

    assert APPROVAL_REQUEST_PATTERN.search(passing_mention) is not None
    assert solicits_operator(passing_mention) is False


# --- the composition ------------------------------------------------------


def _match(
    category: Category = Category.DECISION_REQUEST,
    *,
    rule_id: str = "persona.decision_request",
    answer_key: str | None = None,
    decision_id: str | None = None,
    solicits: bool = True,
    obstacle: bool = False,
) -> MatchResult:
    return MatchResult(
        category,
        rule_id,
        "I am not deciding that.",
        decision_id=decision_id,
        answer_key=answer_key,
        obstacle_question=obstacle,
        solicits_operator=solicits,
    )


def _engine(gap_stance: str | None = None, persona_name: str = "exec-proxy") -> OperatorEngine:
    script = make_script()
    if gap_stance is not None:
        object.__setattr__(script.answer_sheet, "gap_stance", gap_stance)
    object.__setattr__(script, "persona", load_persona(ROOT / f"scenarios/_personas/{persona_name}.yaml"))
    return OperatorEngine(script, InMemoryTransport([]), driver=driver(lambda _view: "x"))


def test_a_declared_answer_is_the_only_directive_that_carries_substance() -> None:
    engine = _engine()
    assert engine._resolve_directive(_match(answer_key="grain_fact"), answer_available=True) == "answer"
    assert engine._resolve_directive(_match(decision_id="choice"), answer_available=True) == "answer"
    # No prior match at all (turn one) is treated the same way: there is
    # nothing to suppress and the scripted opening carries the turn.
    assert engine._resolve_directive(None, answer_available=False) == "answer"


def test_a_turn_nobody_asked_anything_on_yields() -> None:
    engine = _engine()
    assert engine._resolve_directive(_match(solicits=False), answer_available=False) == "yield"
    # Yield outranks the persona: an operator that refuses a decision nobody
    # requested is the exact failure this replaces.
    assert engine._resolve_directive(
        _match(Category.APPROVAL_REQUEST, solicits=False), answer_available=False
    ) == "yield"


def test_a_factual_gap_takes_the_scenario_stance_not_the_persona_one() -> None:
    short = _engine(gap_stance="source_is_short")
    fine = _engine(gap_stance="operator_is_uninformed")
    ask = _match(Category.SOURCE_QUESTION, rule_id="unmatched.source_question")

    assert short._resolve_directive(ask, answer_available=False) == "unknown_fact:source_is_short"
    assert fine._resolve_directive(ask, answer_available=False) == "unknown_fact:operator_is_uninformed"
    # Same persona in both. The scenario, not the personality, decides what a
    # missing answer means -- only the answer sheet can be checked against the
    # gold the run is graded on.
    assert short.script.persona.id == fine.script.persona.id


def test_an_obstacle_question_never_borrows_the_scenarios_gap_stance() -> None:
    """An obstacle is infrastructure, not a claim about the source.

    Under ``source_is_short`` the operator would otherwise assert "my data
    genuinely cannot answer that" about a 403 or a timeout -- a factual claim
    the answer sheet never made. It resolves before the choice override too:
    "Which option: request write permission, or proceed read-only?" is
    choice-shaped, and routing it to a ``assert_default`` persona asks for a
    firm opinion about infrastructure, which is exactly what the no-leading
    guard exists to prevent.
    """

    engine = _engine(gap_stance="source_is_short", persona_name="confidently-wrong")
    obstacle = _match(Category.OTHER, rule_id="fallback.no-leading", obstacle=True)

    assert engine._resolve_directive(
        obstacle, answer_available=False
    ) == "unknown_fact:operator_is_uninformed"
    # Choice vocabulary does not promote it to a decision.
    assert engine._resolve_directive(
        obstacle,
        answer_available=False,
        agent_message="Which option: request write permission, or proceed read-only?",
    ) == "unknown_fact:operator_is_uninformed"


def test_a_decision_takes_the_persona_stance_not_the_scenario_one() -> None:
    ask = _match(Category.APPROVAL_REQUEST, rule_id="persona.approval_request")
    for persona_name, expected in (
        ("exec-proxy", "defer_upward"),
        ("impatient", "push_for_speed"),
        ("rubber-stamper", "approve_anything"),
        ("confidently-wrong", "assert_default"),
        ("micromanager", "ask_back"),
    ):
        engine = _engine(gap_stance="source_is_short", persona_name=persona_name)
        assert engine._resolve_directive(ask, answer_available=False) == f"decision:{expected}"


# --- what the engine does with it -----------------------------------------


def test_a_yielded_turn_transmits_the_authors_room_turn_not_a_persona_line() -> None:
    """The room turns an author writes were previously unreachable text.

    ``base`` fell through to ``scripted_turn.text`` only when ``next_reply``
    was falsy, and the matcher always returns something, so "Please continue."
    never went out on a substitutable turn -- on either the scripted or the
    driven path. The operator said "I don't know, you tell me." where the
    author had written room for the agent to work.
    """

    script = make_script(
        turns=("Improve weekly visibility.", "Take your time.", "Please continue.")
    )
    transport = InMemoryTransport(
        [
            TurnResult(agent_message="Blueprint: approved. Building it now."),
            TurnResult(agent_message="Still building; nothing needed from you."),
            TurnResult(agent_message="Done.", reported=True),
        ]
    )
    OperatorEngine(script, transport).run()

    assert transport.message_texts[1] == "Take your time."
    assert transport.message_texts[2] == "Please continue."


def test_a_stock_line_is_never_handed_to_the_driver_as_substance() -> None:
    """The primary cause of the refusal collapse, pinned.

    The prompt tells the driver that a non-empty ``selected_reply`` is the
    substance the turn expects. Passing a persona bank line there made the
    driver paraphrase a refusal -- faithfully, which is why it never tripped
    any of the rejection ladders.
    """

    script = make_script(turns=("Improve weekly visibility.", "Please continue."))
    views: list[DriverView] = []

    def provider(view: DriverView) -> str:
        views.append(view)
        return "Understood, carry on."

    OperatorEngine(
        script,
        InMemoryTransport(
            [
                TurnResult(agent_message="Which option should I pick?"),
                TurnResult(agent_message="Done.", reported=True),
            ]
        ),
        driver=driver(provider),
    ).run()

    assert len(views) == 1
    assert views[0].selected_reply == ""
    assert views[0].directive.startswith("decision:")
    # The brief is still offered in full: having nothing *declared* to say is
    # not the same as knowing nothing.
    assert len(views[0].known_facts) == 2


def test_a_declared_answer_still_reaches_the_driver_as_substance() -> None:
    script = make_script(turns=("Improve weekly visibility.", "Please continue."))
    views: list[DriverView] = []

    def provider(view: DriverView) -> str:
        views.append(view)
        return "Understood, carry on."

    OperatorEngine(
        script,
        InMemoryTransport(
            [
                TurnResult(agent_message="What is the grain?"),
                TurnResult(agent_message="Done.", reported=True),
            ]
        ),
        driver=driver(provider),
    ).run()

    assert views[0].directive == "answer"
    assert views[0].selected_reply == "The grain is one row per account; FACT-ONLY-MARKER."


# --- the two new declared keys --------------------------------------------


def test_every_shipped_persona_declares_a_stance() -> None:
    """A default would silently make every persona deflect identically.

    All seven banks already share the byte-identical fallback "I don't know,
    you tell me.", which is why the collapse was never exec-proxy-specific.
    """

    for path in sorted((ROOT / "scenarios/_personas").glob("*.yaml")):
        card = load_persona(path)
        assert card.stance_when_unknown in STANCE_WHEN_UNKNOWN, path.name
        assert "stance_when_unknown" in path.read_text(encoding="utf-8"), path.name


def test_an_unknown_stance_is_a_load_error() -> None:
    raw = dict(load_persona(ROOT / "scenarios/_personas/smoke.yaml").to_mapping())
    raw["stance_when_unknown"] = "shrug"
    with pytest.raises(PersonaError, match="stance_when_unknown"):
        from dp_scenarios.operator.persona import persona_from_mapping

        persona_from_mapping(raw)


def test_gap_stance_defaults_and_rejects_anything_else() -> None:
    base = {
        "version": 1,
        "scenario_id": "s",
        "opening_message": "Improve weekly visibility.",
        "turns": ["Improve weekly visibility."],
        "source_answers": {},
        "decision_answers": {},
        "status_answers": {},
        "opening_forbidden_terms": ["grain"],
        "open_decision_markers": ["[DECISION NEEDED]"],
        "obstacle_terms": [],
    }
    assert answer_sheet_from_mapping(base).gap_stance == DEFAULT_GAP_STANCE
    assert DEFAULT_GAP_STANCE in GAP_STANCES
    for stance in GAP_STANCES:
        assert answer_sheet_from_mapping({**base, "gap_stance": stance}).gap_stance == stance
    with pytest.raises(AnswerSheetError, match="gap_stance"):
        answer_sheet_from_mapping({**base, "gap_stance": "whatever"})


def test_capability_shortfall_declares_the_short_source_stance() -> None:
    """The one shipped scenario whose drill *is* the shortfall.

    An operator that softens it -- "I'm not sure, have a look" -- sends the
    agent looking for history that does not exist, and the disclosure the
    scenario grades stops being visible from the conversation.
    """

    from dp_scenarios.scenario import load_scenario

    scenario = load_scenario(ROOT / "scenarios/capability-shortfall")
    assert scenario.answer_sheet.gap_stance == "source_is_short"
    assert scenario.persona.stance_when_unknown == "defer_upward"


def test_a_rejected_driver_falls_back_to_the_script_not_to_a_stock_refusal() -> None:
    """The fallback must follow the same rule as ``selected_reply``.

    A driver rejected twice transmits the fallback verbatim. Leaving that as
    ``next_reply`` would put the persona's stock line back on the wire on
    exactly the turns the directive exists to keep it off -- and it would do so
    silently, because every other signal (mode, counters, failure mode) reads
    the same either way. Mutating this line back was the one change the rest of
    the suite did not notice.
    """

    script = make_script(turns=("Improve weekly visibility.", "Please continue."))

    # Always leads, so both attempts are rejected and the ladder falls back.
    def provider(_view: DriverView) -> str:
        return "The grain is what matters here."

    transport = InMemoryTransport(
        [
            TurnResult(agent_message="Which option should I pick?"),
            TurnResult(agent_message="Done.", reported=True),
        ]
    )
    result = OperatorEngine(script, transport, driver=driver(provider)).run()

    assert result.turns[1].operator_mode == "driver_fallback"
    assert transport.message_texts[1] == "Please continue."
    assert transport.message_texts[1] != script.persona.replies_for("decision_request")[0]


def test_a_repeat_suppressed_turn_is_not_treated_as_having_substance() -> None:
    """A suppressed fact must behave as "no declared answer", not as turn one.

    Discarding the match on suppression made ``_resolve_directive`` see
    ``None`` and return ``answer`` -- so the driver was told
    ``selected_reply`` held the turn's substance while being handed the empty
    string. The prompt defines ``answer`` as "``selected_reply`` holds the
    substance"; empty substance is undefined and invites the model to make one
    up. Two turns of the live run sat in exactly this state.
    """

    script = make_script(turns=("Improve weekly visibility.", "Please continue.", "Go on."))
    views: list[DriverView] = []

    def provider(view: DriverView) -> str:
        views.append(view)
        # Actually convey the fact, so the served-fact memory records it and
        # the immediate re-ask is suppressed. A deflecting driver would not
        # consume the fact, which is a different (already tested) path.
        return view.selected_reply or "Understood, carry on."

    OperatorEngine(
        script,
        InMemoryTransport(
            [
                TurnResult(agent_message="What is the grain?"),
                TurnResult(agent_message="What is the grain?"),
                TurnResult(agent_message="Done.", reported=True),
            ]
        ),
        driver=driver(provider),
    ).run()

    assert views[0].directive == "answer"
    assert views[0].selected_reply != ""
    # Second ask: the fact was served, so it is suppressed. The turn now has
    # no substance and must not claim to.
    assert views[1].selected_reply == ""
    # The concrete value, not merely "not answer": a re-ask is still an ask,
    # so it must not collapse to ``yield``. "What is the grain?" carries no
    # choice vocabulary, so it is a factual gap -- the operator has already
    # said its piece and the agent can go and look.
    assert views[1].directive == "unknown_fact:operator_is_uninformed"


def test_the_generated_surface_path_yields_too() -> None:
    """A rendered persona line is still a refusal nobody asked for.

    ``TierRunner`` wires a ``GeneratedOperator`` in, so this is a live path,
    and it took the ``elif`` branch straight past the yield rule.
    """

    from dp_scenarios.operator.generated import GeneratedOperator

    script = make_script(turns=("Improve weekly visibility.", "Take your time."))
    consulted: list[object] = []

    def provider(view: object) -> str:
        consulted.append(view)
        return "Paraphrased: I don't know, you tell me."

    transport = InMemoryTransport(
        [
            TurnResult(agent_message="Blueprint: approved. Building it now."),
            TurnResult(agent_message="Done.", reported=True),
        ]
    )
    OperatorEngine(script, transport, generated_operator=GeneratedOperator(provider)).run()

    assert consulted == [], "a yielded turn must not reach a rendering provider"
    assert transport.message_texts[1] == "Take your time."


def test_a_choice_survives_a_coarse_source_classification() -> None:
    """The rule bank fires ``source.question`` on vocabulary too common to mean anything.

    ``matcher.py``'s first rule matches ``data|field|row|table|input``, so an
    explicit either/or lands there and the operator answers "I do not have
    that" to a question about which path to take -- leaving the choice unmade,
    which is the stall this whole change exists to remove.
    """

    from dp_scenarios.operator.matcher import Category

    engine = _engine(gap_stance="source_is_short", persona_name="exec-proxy")
    message = "Which option do you want? The data supports both."
    coarse = _match(Category.SOURCE_QUESTION, rule_id="unmatched.source_question")

    assert engine._resolve_directive(
        coarse, answer_available=False, agent_message=message
    ) == "decision:defer_upward"
    # Without the choice vocabulary the same classification routes factually.
    assert engine._resolve_directive(
        coarse, answer_available=False, agent_message="Where does the data come from?"
    ) == "unknown_fact:source_is_short"


def test_a_status_question_never_borrows_the_scenarios_gap_stance() -> None:
    """"Is it done on your side?" is not a claim about what the source holds."""

    from dp_scenarios.operator.matcher import Category

    engine = _engine(gap_stance="source_is_short")
    ask = _match(Category.STATUS_QUERY, rule_id="unmatched.status_query")
    assert engine._resolve_directive(
        ask, answer_available=False, agent_message="Is the report done on your side?"
    ) == "unknown_fact:operator_is_uninformed"


def test_the_scenarios_spoiler_fact_is_governed_by_a_forbidden_term() -> None:
    """Offering the whole brief removes the structural guard; the term restores it.

    ``updated_at_meaning`` is the fact that resolves capability-shortfall. It
    now sits in ``known_facts`` on every turn, so the only thing stopping the
    driver volunteering it is the leading scan -- which can only see terms the
    scenario declares.
    """

    from dp_scenarios.scenario import load_scenario

    scenario = load_scenario(ROOT / "scenarios/capability-shortfall")
    sheet = scenario.answer_sheet
    assert "updated_at_meaning" in sheet.ground_truth
    assert "updatedat" in [term.casefold() for term in sheet.driver_forbidden_terms]


def test_an_event_still_fires_on_a_yielded_turn() -> None:
    """Yielding changes the words, never the schedule."""

    from dp_scenarios.operator.events import EventSchedule, event_from_mapping

    card = event_from_mapping(
        {
            "version": 1,
            "id": "deadline",
            "trigger_turn": 2,
            "type": "deadline_pressure",
            "content": "The board meets Friday.",
            "outcome": "deadline_recorded",
            "required_terms": ["Friday"],
        }
    )
    script = make_script(
        turns=("Improve weekly visibility.", "Take your time."),
        events=EventSchedule((card,)),
    )
    transport = InMemoryTransport(
        [
            TurnResult(agent_message="Blueprint: approved. Building it now."),
            TurnResult(agent_message="Done.", reported=True),
        ]
    )
    result = OperatorEngine(script, transport).run()

    assert result.fired_event_ids == ("deadline",)
    assert "Friday" in transport.message_texts[1]
    assert "Take your time." in transport.message_texts[1]


def test_a_partial_term_match_does_not_exempt_a_multi_term_fact() -> None:
    """The exemption must mirror the matcher's own all-terms rule.

    ``answer_for_ground_truth`` fires a fact only when its *whole* declared
    term set is present, so a fact keyed on ("exact", "sitting", "stage") is
    not the answer to a message that merely says "stage". Exempting on ``any``
    term let one common word unlock graded vocabulary the agent had not
    reached -- the leading scan still ran, over a term that was no longer in
    it.
    """

    from dp_scenarios.operator.answer_sheet import answer_sheet_from_mapping
    from dp_scenarios.operator.engine import OperatorScript
    from dp_scenarios.operator.events import EventSchedule

    opening = "Improve weekly visibility."
    sheet = answer_sheet_from_mapping(
        {
            "version": 1,
            "scenario_id": "partial-term-test",
            "opening_message": opening,
            "turns": [opening, "Please continue."],
            "source_answers": {},
            "decision_answers": {},
            "status_answers": {},
            "opening_forbidden_terms": ["proxy"],
            "open_decision_markers": ["[DECISION NEEDED]"],
            "obstacle_terms": [],
            "driver_forbidden_terms": ["proxy"],
            "ground_truth": {
                "history": {
                    "terms": ["exact", "sitting", "stage"],
                    "fact": "There is no stage history; a proxy is the only option.",
                }
            },
        }
    )
    turns = tuple(sheet.turns)
    script = OperatorScript.from_components(
        load_persona(ROOT / "scenarios/_personas/smoke.yaml"),
        sheet,
        turns=turns,  # type: ignore[arg-type]
        events=EventSchedule(()),
        turn_budget=len(turns),
        sentinel=None,
        phase_by_turn={index: min(index, 7) for index in range(1, len(turns) + 1)},
    )

    views: list[DriverView] = []

    def provider(view: DriverView) -> str:
        views.append(view)
        return "Understood, carry on."

    OperatorEngine(
        script,
        InMemoryTransport(
            [
                # One of the three terms. Not the fact's question.
                TurnResult(agent_message="How does a deal move to the next stage?"),
                TurnResult(agent_message="Done.", reported=True),
            ]
        ),
        driver=driver(provider),
    ).run()

    assert len(views) == 1
    # Offered, because the brief is always offered whole...
    assert [key for key, _ in views[0].known_facts] == ["history"]
    # ...but not sayable: the agent has not asked the question this fact answers.
    assert "proxy" in views[0].forbidden_terms


def test_a_stray_backtick_cannot_swallow_a_question_on_another_line() -> None:
    """Inline code spans are single-line, so a stray tick cannot eat prose.

    A greedy ``[^`]*`` span ran to the next backtick *anywhere* in the message.
    Agent messages here are routinely multi-line and routinely contain code
    spans, so an unmatched tick early on consumed everything up to the next
    real span -- taking a genuine question mark with it and silently turning a
    direct ask into a yield.

    The guard is the newline, so the message below must span lines: within one
    line the greedy and bounded forms behave identically, and a single-line
    fixture asserts nothing.
    """

    message = "I set `limit and stopped. Which grain do you want?\nSee `docs` for the rest."
    assert "\n" in message, "the fixture must span lines or it tests nothing"
    assert solicits_operator(message) is True
    assert asks_for_a_choice(message) is True


def test_the_directive_is_recorded_only_where_it_governed_the_turn() -> None:
    """The mechanism has to be legible in the evidence that found the bug.

    Reading ledger annotations is how the refusal collapse was diagnosed. An
    unrecorded directive makes a yielded room turn byte-identical to any other
    room turn, and a yield caused by a *missed* question indistinguishable from
    a deliberate pause. It is deliberately absent on turns it cannot govern --
    turn one, a non-substitutable turn and an approval turn all transmit their
    declared line regardless -- so a value there would describe nothing.
    """

    script = make_script()
    result = OperatorEngine(
        script,
        InMemoryTransport(
            [
                TurnResult(agent_message="Which option should I pick?"),
                TurnResult(agent_message="Nothing needed from you."),
                TurnResult(agent_message="Please approve."),
                TurnResult(agent_message="Building."),
                TurnResult(agent_message="Done.", reported=True),
            ]
        ),
    ).run()

    directives = [turn.operator_directive for turn in result.turns]
    assert directives[0] == "answer", "turn one transmits its declared line"
    # Turn 2 is substitute_reply: False and turn 4 is the approval turn.
    assert directives[1] == "answer"
    assert directives[3] == "answer"
    # Turn 3 followed "Nothing needed from you."
    assert directives[2] == "yield"

    claims = [row.get("claim") or {} for row in result.ledger_rows]
    assert claims[2].get("operator_directive") == "yield"
    assert "operator_directive" not in claims[0]
    assert "operator_directive" not in claims[3]


def test_the_conversation_file_names_the_directive() -> None:
    """The rendered transcript is the artifact a human actually reads.

    Recording the directive in the ledger is not enough on its own: the
    refusal collapse was diagnosed from the conversation file, so a turn the
    operator had nothing to say on has to announce that there, next to the
    rule that selected it.
    """

    from dp_scenarios.runner.transcript import _classification_note, _Turn

    turn = _Turn(
        1,
        {"agent_message": "Nothing needed from you."},
        {
            "operator_matched": False,
            "operator_answered_from_ground_truth": False,
            "operator_rule_id": "persona.approval_request",
            "operator_directive": "yield",
        },
    )
    note = _classification_note(turn)
    assert "directive=yield" in note

    # An ``answer`` turn records nothing, so nothing is rendered.
    plain = _Turn(
        2,
        {"agent_message": "What is the grain?"},
        {
            "operator_matched": True,
            "operator_answered_from_ground_truth": True,
            "operator_rule_id": "ground_truth.grain_fact",
        },
    )
    assert "directive=" not in _classification_note(plain)


def test_the_persona_stance_is_script_identity() -> None:
    """An engine input must be hashed, exactly like its scenario-axis twin.

    ``gap_stance`` reaches the hash through the answer sheet's mapping. The
    persona's half did not, so flipping a persona from ``ask_back`` to
    ``assert_default`` -- which changes what the operator says on every turn it
    has no declared answer for -- left ``operator_script_hash`` byte-identical,
    and the paired-comparison guard would have read two different operators as
    the same script.

    ``label``, ``vocabulary`` and ``behaviors`` stay out on purpose: they are
    prompt colour, not a branch the engine takes.
    """

    from dataclasses import replace as dc_replace

    from dp_scenarios.operator.engine import operator_script_hash
    from dp_scenarios.operator.persona import persona_from_mapping

    script = make_script()
    raw = dict(script.persona.to_mapping())
    assert raw["stance_when_unknown"] != "assert_default"
    flipped = persona_from_mapping({**raw, "stance_when_unknown": "assert_default"})

    assert operator_script_hash(
        dc_replace(script, persona=flipped)
    ) != operator_script_hash(script)

    # Prompt colour is still excluded, so this test cannot pass for the wrong
    # reason -- it is the stance that moved the hash, not any persona edit.
    recoloured = persona_from_mapping({**raw, "label": "A different label"})
    assert operator_script_hash(
        dc_replace(script, persona=recoloured)
    ) == operator_script_hash(script)


def test_a_bare_confirm_is_an_ask_on_any_line() -> None:
    """The one anchored alternative needs MULTILINE; agent messages wrap.

    Without it "Blueprint is ready.\\nConfirm the metric definition" matched
    nothing at all -- the anchor only reaches offset 0 of the whole message --
    so a direct instruction on the second line was dropped as a yield.
    """

    message = "Blueprint is ready.\nConfirm the metric definition and I will build."
    assert "\n" in message, "the fixture must span lines or it tests nothing"
    assert solicits_operator(message) is True
    # The single-line form must keep working, so this is a widening only.
    assert solicits_operator("Confirm the metric definition and I will build.") is True
    # Still not the agent's own report.
    assert solicits_operator("I can confirm that the build finished cleanly.") is False


def test_which_opens_an_ask_without_opening_a_question() -> None:
    """``which`` solicits an answer but must not widen the classifier.

    ``_classify``'s ``is_question`` gates the obstacle branch, which returns a
    different category, rule id, reply and ``matched`` flag -- so adding a word
    there moves ledger rows. It belongs to the solicitation test alone, which
    is why the two openers are separate constants.
    """

    from dp_scenarios.operator.matcher import MatcherBank

    # No question mark, and deliberately no request phrase either: "do you
    # want" would match SOLICITATION_PATTERN on its own and leave the opener
    # untested. Only the ``which`` opener can see this as an ask.
    from dp_scenarios.operator.matcher import (
        INTERROGATIVE_OPENER_PATTERN,
        SOLICITATION_PATTERN,
    )

    bare = "Which grain, account or deal."
    assert not SOLICITATION_PATTERN.search(bare), "fixture must not match another alternative"
    assert not INTERROGATIVE_OPENER_PATTERN.match(bare)
    assert solicits_operator(bare) is True

    bank = MatcherBank(
        load_persona(ROOT / "scenarios/_personas/smoke.yaml"),
        make_script().answer_sheet,
    )
    # An obstacle term, no question mark, opening with "Which". Treating it as
    # a question would divert it to the no-leading fallback and mark the turn
    # unmatched.
    result = bank.reply_for("Which table should I use for the proxy join")
    assert result.rule_id != "fallback.no-leading"
    assert result.obstacle_question is False
    assert result.matched is True

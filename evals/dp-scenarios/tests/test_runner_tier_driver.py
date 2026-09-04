"""End-to-end qualification and wiring guards for the driver operator."""

from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path
from types import SimpleNamespace

import aiohttp
import pytest

from dp_scenarios.operator import (
    DriverOperator,
    EventSchedule,
    OperatorEngine,
    OperatorScript,
    event_from_mapping,
)
from dp_scenarios.operator.answer_sheet import answer_sheet_from_mapping
from dp_scenarios.operator.transport import InMemoryTransport, TurnResult
from dp_scenarios.runner import (
    ReplayMismatch,
    RecordingSession,
    RunEnvironment,
    RunEnvironmentError,
    TierError,
    TierRunner,
)
from dp_scenarios.runner.environment import PinnedVersions
from dp_scenarios.scenario import GateSpec
from dp_scenarios.grading.score import ScoreVector, TerminalState as ScoreTerminalState
from dp_scenarios.runner.qualification import (
    QualificationDisposition,
    QualificationRecord,
    qualify_run,
)
from dp_scenarios.runner.tier import _promote_certified_run, _replay_verification
from dp_scenarios.runner.transcript import render_epoch_conversation

from test_runner_tier import clean_canary, make_scenario, pins, recording_for


def _scenario(name: str = "driver-e2e", *, turns: int = 3):
    base = make_scenario(name, turns=turns)
    sheet = answer_sheet_from_mapping(
        {
            **base.script.answer_sheet.to_mapping(),
            "driver_forbidden_terms": ["leak"],
            "ground_truth": {
                "grain": {
                    "terms": ["grain"],
                    "fact": "The grain is one row per account.",
                }
            },
        }
    )
    script = OperatorScript.from_components(
        base.script.persona,
        sheet,
        turns=base.script.turns,
        turn_budget=base.script.turn_budget,
        phase_by_turn=base.script.phase_by_turn,
    )
    return replace(base, script=script)


def _driver_pins(model_id: str = "fake-driver", temperature: float = 0.0) -> PinnedVersions:
    return replace(
        pins(),
        driver_model_id=model_id,
        driver_sampling_params={"temperature": temperature},
    )


def _responses() -> list[TurnResult]:
    return [
        TurnResult(agent_message="What is the source?"),
        TurnResult(agent_message="Status update."),
        TurnResult(agent_message="Done.", reported=True),
    ]


def fake_provider(view: object) -> str:
    return f"Turn {view.turn}: carry on."


def _driver(provider=fake_provider, *, model_id: str = "fake-driver") -> DriverOperator:
    return DriverOperator(provider, model_id=model_id, temperature=0.0)


@pytest.fixture(autouse=True)
def no_network(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("driver qualification tests must not use the network")

    monkeypatch.setattr(aiohttp, "ClientSession", fail)


def test_driver_e2e_session_factory_uses_driver_words_and_records_qualification(
    tmp_path: Path,
) -> None:
    scenario = _scenario()
    transports: list[InMemoryTransport] = []

    def session_factory(*_args: object) -> InMemoryTransport:
        transport = InMemoryTransport(_responses())
        transports.append(transport)
        return transport

    result = TierRunner(
        [scenario],
        pins=_driver_pins(),
        canary=clean_canary(),
        session_factory=session_factory,
        operator_factory=lambda: _driver(),
        evidence_root=tmp_path / "evidence",
    ).run()

    assert len(transports) == 1
    assert [message.text for message in transports[0].sent_messages][1:] == [
        "Turn 2: carry on.",
        "Turn 3: carry on.",
    ]
    run = result.scenario_runs[0]
    bundle = Path(run.evidence_bundle_dir)
    manifest = json.loads((bundle / "manifest.json").read_text(encoding="utf-8"))
    observations = json.loads(
        (bundle / "artifacts" / "operator-observations.json").read_text(encoding="utf-8")
    )
    qualification = json.loads((bundle / "qualification.json").read_text(encoding="utf-8"))
    assert manifest["driver_model_id"] == "fake-driver"
    assert manifest["driver_sampling_params"] == {"temperature": 0.0}
    assert observations["operator_mode"] == "driver"
    assert qualification["operator_mode"] == "driver"
    assert qualification["replay_status"] == "not-attempted"


def test_driver_e2e_replay_uses_driver_and_rejects_different_words(tmp_path: Path) -> None:
    scenario = _scenario("driver-replay")
    recorder = RecordingSession(InMemoryTransport(_responses()))
    OperatorEngine(scenario.script, recorder, driver=_driver()).run()
    recording = recorder.recording()

    from dp_scenarios.runner.session import ReplaySession

    replay_session = ReplaySession(recording)
    run_result = OperatorEngine(scenario.script, replay_session, driver=_driver()).run()
    assert [turn.operator_message.text for turn in run_result.turns] == [
        turn.operator_message.text for turn in recording.turns
    ]
    assert [message.text for message in replay_session.sent_messages] == [
        turn.operator_message.text for turn in recording.turns
    ]

    result = TierRunner(
        [scenario],
        pins=_driver_pins(),
        canary=clean_canary(),
        replay_recordings={scenario.id: recording},
        operator_factory=lambda: _driver(),
        evidence_root=tmp_path / "positive",
    ).run()
    assert result.scenario_runs[0].replay_recording is recording

    different_recorder = RecordingSession(InMemoryTransport(_responses()))
    OperatorEngine(
        scenario.script,
        different_recorder,
        driver=_driver(lambda _view: "Different driver wording."),
    ).run()
    different = different_recorder.recording()
    with pytest.raises(ReplayMismatch):
        TierRunner(
            [scenario],
            pins=_driver_pins(),
            canary=clean_canary(),
            replay_recordings={scenario.id: different},
            operator_factory=lambda: _driver(),
            evidence_root=tmp_path / "negative",
        ).run()


def test_driver_replay_verification_is_not_attempted_but_scripted_replay_mismatches() -> None:
    scenario = _scenario("driver-verification")
    recorder = RecordingSession(InMemoryTransport(_responses()))
    OperatorEngine(scenario.script, recorder, driver=_driver()).run()
    recording = recorder.recording()
    expected = SimpleNamespace(ledger_bytes=b"", operator_message_bytes=b"")

    assert _replay_verification(
        scenario,
        recording,
        expected,
        generated_operator=False,
        driver=True,
    ) == ("not-attempted", "driver operator output is not assumed deterministic")
    assert _replay_verification(
        scenario,
        recording,
        expected,
        generated_operator=False,
        driver=False,
    )[0] == "mismatch"


def test_driver_leading_term_falls_back_on_both_runner_branches(tmp_path: Path) -> None:
    scenario = _scenario("driver-leading")

    def leaking_provider(view: object) -> str:
        if view.turn == 2:
            return "leak"
        return f"Turn {view.turn}: carry on."

    transports: list[InMemoryTransport] = []

    def session_factory(*_args: object) -> InMemoryTransport:
        transport = InMemoryTransport(_responses())
        transports.append(transport)
        return transport

    live = TierRunner(
        [scenario],
        pins=_driver_pins(),
        canary=clean_canary(),
        session_factory=session_factory,
        operator_factory=lambda: _driver(leaking_provider),
        evidence_root=tmp_path / "live",
    ).run()
    assert [message.text for message in transports[0].sent_messages][1] == scenario.script.answer_sheet.source_answers["source"]
    live_observations = json.loads(
        (
            Path(live.scenario_runs[0].evidence_bundle_dir)
            / "artifacts"
            / "operator-observations.json"
        ).read_text(encoding="utf-8")
    )
    assert live_observations["driver_leading_rejected_count"] == 1

    recorder = RecordingSession(InMemoryTransport(_responses()))
    OperatorEngine(scenario.script, recorder, driver=_driver(leaking_provider)).run()
    recording = recorder.recording()
    assert recording.turns[1].operator_message.text == scenario.script.answer_sheet.source_answers["source"]
    replay = TierRunner(
        [scenario],
        pins=_driver_pins(),
        canary=clean_canary(),
        replay_recordings={scenario.id: recording},
        operator_factory=lambda: _driver(leaking_provider),
        evidence_root=tmp_path / "replay",
    ).run()
    replay_bundle = Path(replay.scenario_runs[0].evidence_bundle_dir)
    replay_recording = json.loads(
        (replay_bundle / "session-replay.json").read_text(encoding="utf-8")
    )
    assert replay_recording["turns"][1]["operator_message"]["text"] == scenario.script.answer_sheet.source_answers["source"]
    replay_observations = json.loads(
        (replay_bundle / "artifacts" / "operator-observations.json").read_text(encoding="utf-8")
    )
    assert replay_observations["driver_leading_rejected_count"] == 1


def test_driver_pins_and_factory_are_consistent_before_running_a_session(tmp_path: Path) -> None:
    scenario = _scenario("driver-gates")
    called = False

    def forbidden_session(*_args: object) -> InMemoryTransport:
        nonlocal called
        called = True
        raise AssertionError("session factory must not be called")

    # The canary is the *first* thing the tier spends: it extracts claims and,
    # in a live run, preflights and builds. "Fail before entering any
    # environment" therefore has to mean before the canary, not merely before
    # a session -- and only a canary factory can witness that, because a
    # ``CanaryResult`` value passed in has already been computed by the
    # caller. Asserting on ``session_factory`` alone leaves the guard free to
    # sit anywhere in ``run()`` after ``_canary()`` and still look correct.
    canary_calls = 0

    def counting_canary() -> object:
        nonlocal canary_calls
        canary_calls += 1
        return clean_canary()

    with pytest.raises(TierError, match="require an operator factory"):
        TierRunner(
            [scenario],
            pins=_driver_pins(),
            canary=counting_canary,
            session_factory=forbidden_session,
        ).run()
    assert not called
    assert canary_calls == 0

    with pytest.raises(TierError, match="pins and operator factory disagree"):
        TierRunner(
            [scenario],
            pins=pins(),
            canary=clean_canary(),
            replay_recordings={scenario.id: recording_for(scenario, _responses())},
            operator_factory=lambda: _driver(),
        ).run()

    # The per-epoch consistency gate is the one that *does* sit downstream of
    # the canary, so the same factory is consulted here. That pins the
    # assertion above to ordering rather than to a canary this runner would
    # never have called anyway.
    with pytest.raises(TierError, match="pins and operator factory disagree"):
        TierRunner(
            [scenario],
            pins=_driver_pins(model_id="expected-driver"),
            canary=counting_canary,
            replay_recordings={scenario.id: recording_for(scenario, _responses())},
            operator_factory=lambda: _driver(),
        ).run()
    assert canary_calls == 1


def test_stored_driver_manifest_is_rejected_by_na_pins(tmp_path: Path) -> None:
    scenario = _scenario("driver-stored-manifest")
    source_root = tmp_path / "source"
    source_root.mkdir()
    with RunEnvironment(scenario, _driver_pins(), root=source_root) as environment:
        stored_manifest = environment.manifest.to_dict()
    recorder = RecordingSession(InMemoryTransport(_responses()))
    OperatorEngine(scenario.script, recorder).run()
    recording = replace(recorder.recording(), manifest=stored_manifest)

    evidence_root = tmp_path / "evidence"
    with pytest.raises(RunEnvironmentError, match="replay manifest mismatch in driver_model_id"):
        TierRunner(
            [scenario],
            pins=pins(),
            canary=clean_canary(),
            replay_recordings={scenario.id: recording},
            operator_factory=None,
            evidence_root=evidence_root,
        ).run()
    assert list(evidence_root.rglob("manifest.json")) == []
    assert not (evidence_root / scenario.id).exists()


def test_a_driver_run_is_never_promoted_to_certified(tmp_path: Path) -> None:
    """Repeatability certification must not launder a driver run into CERTIFIED."""

    scenario = _scenario("driver-promotion")

    def session_factory(*_args: object) -> InMemoryTransport:
        return InMemoryTransport(_responses())

    result = TierRunner(
        [scenario],
        pins=_driver_pins(),
        canary=clean_canary(),
        session_factory=session_factory,
        operator_factory=lambda: _driver(),
        evidence_root=tmp_path / "evidence",
    ).run()
    run = result.scenario_runs[0]
    assert run.qualification.operator_mode == "driver"

    # A live, passing, replay-verified driver run: every precondition for
    # certification except the operator's words having come from a model.
    live = replace(
        run,
        manifest=replace(
            run.manifest,
            validation_mode="live",
            supervisor_binary_path="/opt/nxd-desktop-supervisor",
            session_root="/tmp/desktop-session",
            session_config_path="/tmp/desktop-session/mcp-config.json",
            session_config_sha256="sha256:config",
            session_trace_path="/tmp/desktop-session/trace.jsonl",
            session_server_result_path="/tmp/desktop-session/server-result.json",
        ),
        replay_verification_status="verified",
        score=ScoreVector({}, 100, {}, ScoreTerminalState.PASSED),
        qualification=QualificationRecord(
            QualificationDisposition.QUALIFIED,
            "verified",
            "driver",
            ("driver_operator_is_capped_below_certified",),
        ),
    )
    # Control: the same run with a scripted operator DOES certify, so the
    # assertions below can only be carried by the driver cap.
    assert (
        qualify_run(
            live.score,
            replay_status="verified",
            generated_operator=False,
            driver=False,
            repeatability_certified=True,
            validation_mode="live",
        ).disposition
        is QualificationDisposition.CERTIFIED
    )

    promoted = _promote_certified_run(live)

    assert promoted.qualification.disposition is QualificationDisposition.QUALIFIED
    assert promoted.qualification.operator_mode == "driver"
    assert promoted.qualification.reasons == ("driver_operator_is_capped_below_certified",)
    assert (
        json.loads(
            (Path(run.evidence_bundle_dir) / "qualification.json").read_text(encoding="utf-8")
        )["disposition"]
        != "CERTIFIED"
    )


def test_a_gate_declared_sentinel_is_redacted_before_the_driver_on_both_branches(
    tmp_path: Path,
) -> None:
    """A marker planted outside the fixture manifest still must not be sent out.

    ``capability-shortfall`` is the only scenario that can run a driver at all
    (it is the only answer sheet declaring ``driver_forbidden_terms``), it
    declares ``operator.sentinel: null``, and it plants its graded
    ``pii_sentinel`` in the mock-source route table -- a place
    ``marker_values`` never reads.  Redaction is unconditional, so the tier
    must union the gate declarations into the engine's redaction set on both
    of its run branches.
    """

    marker = "pii-sentinel-6f3a9c2e"
    scenario = replace(
        _scenario("driver-gate-sentinel"),
        gates={
            "follow-up": GateSpec(
                "follow-up", "capability_shortfall", {"pii_sentinel": marker}
            )
        },
    )
    leaking_turn = (
        f"I pulled /deals and each record has owner.email, e.g. {marker}@example.invalid. "
        "Should I keep it?"
    )

    def responses() -> list[TurnResult]:
        return [
            TurnResult(agent_message=leaking_turn),
            TurnResult(agent_message="Status update."),
            TurnResult(agent_message="Done.", reported=True),
        ]

    def run_branch(name: str, **runner_kwargs: object) -> list[object]:
        views: list[object] = []

        def capturing(view: object) -> str:
            views.append(view)
            return f"Turn {view.turn}: carry on."  # type: ignore[attr-defined]

        TierRunner(
            [scenario],
            pins=_driver_pins(),
            canary=clean_canary(),
            operator_factory=lambda: _driver(capturing),
            evidence_root=tmp_path / name,
            **runner_kwargs,  # type: ignore[arg-type]
        ).run()
        return views

    live_views = run_branch("live", session_factory=lambda *_args: InMemoryTransport(responses()))

    recorder = RecordingSession(InMemoryTransport(responses()))
    OperatorEngine(scenario.script, recorder, driver=_driver()).run()
    replay_views = run_branch("replay", replay_recordings={scenario.id: recorder.recording()})

    for branch, views in (("live", live_views), ("replay", replay_views)):
        assert views, f"the {branch} branch never consulted the driver"
        first = views[0]
        assert marker not in json.dumps(first.to_mapping()), branch  # type: ignore[attr-defined]
        assert "<redacted-sentinel>" in first.agent_message, branch  # type: ignore[attr-defined]
        # The redaction replaced only the marker: the agent's question, which
        # the driver must still be able to answer, survives intact.
        assert "Should I keep it?" in first.agent_message, branch  # type: ignore[attr-defined]


def test_driver_rejection_evidence_is_marshalled_into_observations_on_both_branches(
    tmp_path: Path,
) -> None:
    """The bundle the transcript reads must show a rejected driver turn as one.

    ``operator-observations.json`` is what ``transcript.py`` renders and what a
    reader inspects after a driven run.  Every earlier tier assertion on these
    keys was zero- or false-valued, so a run whose authored text was rejected
    for an obstacle or a repeat, or whose beat had to be substituted, could
    have been recorded as a clean driver run on either branch.
    """

    event = event_from_mapping(
        {
            "version": 1,
            "id": "scope-creep",
            "trigger_turn": 4,
            "type": "scope_creep",
            "content": "Please add the extra scope.",
            "outcome": "scope_creep_fired",
            "required_terms": ["scope", "refusal"],
        }
    )
    base = _scenario("driver-observations", turns=4)
    scenario = replace(
        base,
        script=OperatorScript.from_components(
            base.script.persona,
            base.script.answer_sheet,
            turns=base.script.turns,
            events=EventSchedule((event,)),
            turn_budget=base.script.turn_budget,
            phase_by_turn=base.script.phase_by_turn,
        ),
    )

    def provider(view: object) -> str:
        if view.turn == 2:  # type: ignore[attr-defined]
            # Operator guidance the matcher's outgoing-surface check rejects.
            return "You should just raise the timeout."
        if view.turn == 3:  # type: ignore[attr-defined]
            # A line the deterministic engine already selected (turn 1's).
            return "Improve visibility."
        # Turn 4 fires a card whose beat terms this never carries.
        return "Understood, carry on."

    def responses() -> list[TurnResult]:
        return [
            TurnResult(agent_message="What is the source?"),
            # "leak" is the scenario's forbidden term; the agent saying it
            # exempts it for the next authored turn.
            TurnResult(agent_message="Should I leak the credentials?"),
            TurnResult(agent_message="Status update."),
            TurnResult(agent_message="Done.", reported=True),
        ]

    bundles: dict[str, Path] = {}

    def observations_for(name: str, **runner_kwargs: object) -> dict:
        result = TierRunner(
            [scenario],
            pins=_driver_pins(),
            canary=clean_canary(),
            operator_factory=lambda: _driver(provider),
            evidence_root=tmp_path / name,
            **runner_kwargs,  # type: ignore[arg-type]
        ).run()
        bundle = Path(result.scenario_runs[0].evidence_bundle_dir)
        bundles[name] = bundle
        return json.loads(
            (bundle / "artifacts" / "operator-observations.json").read_text(encoding="utf-8")
        )

    live = observations_for(
        "live", session_factory=lambda *_args: InMemoryTransport(responses())
    )
    recorder = RecordingSession(InMemoryTransport(responses()))
    OperatorEngine(scenario.script, recorder, driver=_driver(provider)).run()
    replay = observations_for("replay", replay_recordings={scenario.id: recorder.recording()})

    for branch, observations in (("live", live), ("replay", replay)):
        assert observations["driver_obstacle_rejected_count"] == 1, branch
        assert observations["driver_repeat_rejected_count"] == 1, branch
        assert observations["driver_beat_substituted_count"] == 1, branch
        assert observations["driver_leading_rejected_count"] == 0, branch
        turns = observations["turns"]
        assert [turn["driver_obstacle_rejected"] for turn in turns] == [
            False, True, False, False
        ], branch
        assert [turn["driver_repeat_rejected"] for turn in turns] == [
            False, False, True, False
        ], branch
        assert [turn["driver_beat_substituted"] for turn in turns] == [
            False, False, False, True
        ], branch
        assert [turn["driver_fallback_reason"] for turn in turns] == [
            None,
            "driver_obstacle_rejected",
            "driver_repeat_rejected",
            "driver_beat_rejected",
        ], branch
        assert [turn["driver_forbidden_terms_exempted"] for turn in turns] == [
            0, 0, 1, 0
        ], branch

    # The counters are what a human actually reads: render the bundle the tier
    # just wrote, not a hand-built observations mapping.
    for branch, bundle in bundles.items():
        header = render_epoch_conversation(bundle).splitlines()
        operator_line = next(line for line in header if line.startswith("operator:"))
        assert "obstacle-rejected=1" in operator_line, branch
        assert "repeat-rejected=1" in operator_line, branch
        assert "beat-substituted=1" in operator_line, branch

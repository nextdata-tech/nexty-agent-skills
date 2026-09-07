"""Contract tests for the local Claude Code entrypoint helpers."""

from __future__ import annotations

import importlib.util
import json
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace

import pytest

from _repo_paths import REPO_ROOT

from dp_scenarios.runner.tier import TierError
from dp_scenarios.grading.statistics import RepeatabilityTier
from dp_scenarios.scenario import RepeatabilitySpec, load_scenarios


# The adapter resolves evals/desktop_stdio.py relative to --repo-root, so
# the root must be derived from this file, not from the working directory:
# CI runs pytest from evals/dp-scenarios, where Path(".") has no evals/.
# `REPO_ROOT` comes from _repo_paths, which walks up for a marker rather than
# counting parents -- see that module for why the count is not portable.
SCENARIO_ROOT = Path(__file__).resolve().parents[1] / "scenarios"
SCRIPT = Path(__file__).parents[1] / "scripts/run_local_claude.py"


@dataclass(frozen=True)
class _ScenarioStub:
    id: str
    repeatability: RepeatabilitySpec


def _load_runner_module():
    spec = importlib.util.spec_from_file_location("dp_scenarios_run_local_claude", SCRIPT)
    if spec is None or spec.loader is None:
        raise AssertionError(f"could not load {SCRIPT}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_local_runner_selects_declared_scenarios_and_rejects_unknown_ids() -> None:
    module = _load_runner_module()
    scenarios = (SimpleNamespace(id="first"), SimpleNamespace(id="second"))

    assert module._select_scenarios(scenarios, ["second"]) == (scenarios[1],)
    with pytest.raises(TierError, match="unknown scenario id"):
        module._select_scenarios(scenarios, ["missing"])


def test_local_runner_marks_single_epoch_runs_as_demonstrated_once() -> None:
    module = _load_runner_module()
    scenario = _ScenarioStub(
        id="scenario",
        repeatability=RepeatabilitySpec(
            RepeatabilityTier.DETERMINISTIC,
            5,
            "wilson_lower_bound",
            ("build",),
            0.9,
            0.95,
        ),
    )

    configured = module._configure_scenarios((scenario,), [], 1)

    assert configured[0].repeatability.epochs == 1
    assert configured[0].repeatability.tier is RepeatabilityTier.DEMONSTRATED_ONCE


def test_local_runner_leaves_timeout_budget_for_the_adapter() -> None:
    module = _load_runner_module()

    assert module._adapter_timeout(10.0) == pytest.approx(9.0)
    assert module._adapter_timeout(0.1) < 0.1


def test_local_runner_host_home_flag_and_bash_require_a_second_opt_in() -> None:
    module = _load_runner_module()

    args = module.build_parser().parse_args(["--allow-host-home", "--allow-host-home-bash"])
    assert args.allow_host_home is True
    assert args.allow_host_home_bash is True
    assert module.build_parser().parse_args([]).jobs == 1
    assert module.build_parser().parse_args(["--jobs", "2"]).jobs == 2

    with pytest.raises(TierError, match="requires --allow-host-home"):
        module.main(["--allow-host-home-bash"])


def test_local_runner_loads_only_supported_credentials_from_owner_only_env_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _load_runner_module()
    env_file = tmp_path / ".env"
    env_file.write_text(
        "OPENAI_API_KEY=sk-from-file\n"
        "CLAUDE_CODE_OAUTH_TOKEN=oauth-from-file\n"
        "UNRELATED_SECRET=must-not-load\n",
        encoding="utf-8",
    )
    env_file.chmod(0o600)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("CLAUDE_CODE_OAUTH_TOKEN", raising=False)

    credentials = module._load_local_credentials(env_file)

    assert credentials == {
        "OPENAI_API_KEY": "sk-from-file",
        "CLAUDE_CODE_OAUTH_TOKEN": "oauth-from-file",
    }
    assert "UNRELATED_SECRET" not in credentials


def test_oauth_credentials_always_withhold_bash() -> None:
    module = _load_runner_module()
    args = module.build_parser().parse_args([])

    assert module._tool_grant_arguments(args, oauth_token_present=True) == ["--no-bash"]


@pytest.mark.parametrize("jobs", [0, -1])
def test_local_runner_rejects_non_positive_jobs(jobs: int) -> None:
    module = _load_runner_module()

    with pytest.raises(TierError, match="--jobs must be a positive integer"):
        module.main(["--jobs", str(jobs)])


@pytest.mark.parametrize(
    ("cli_arguments", "bash_withheld"),
    [
        (["--allow-host-home"], True),
        (["--allow-host-home", "--allow-host-home-bash"], False),
        ([], False),
    ],
)
def test_host_home_without_bash_reaches_claude_as_a_denial(
    cli_arguments: list[str], bash_withheld: bool
) -> None:
    """Follow the flag all the way to the argv the agent process is spawned with.

    The parsed flag, the adapter flag, and the adapter's own boolean were all
    already correct while a live ``--allow-host-home`` run still made five
    Bash calls against the real host HOME: nothing on the chain ever denied
    the tool, it was only left off an auto-approval list.  This test asserts
    the end of the chain -- what Claude Code is actually told.
    """

    from dp_scenarios.runner import claude_adapter

    module = _load_runner_module()
    args = module.build_parser().parse_args(cli_arguments)
    adapter_flags = module._tool_grant_arguments(args)

    adapter_args = claude_adapter.build_parser().parse_args(
        [
            "--claude", "/usr/bin/true",
            "--plugin-dir", ".",
            "--repo-root", str(REPO_ROOT),
            "--fixture-dir", ".",
            "--artifact-dir", ".",
            "--desktop-supervisor", "/usr/bin/true",
            "--desktop-python", "/usr/bin/true",
            *adapter_flags,
        ]
    )
    adapter = claude_adapter.ClaudeCodeAdapter(
        claude=Path("/usr/bin/true"),
        model="test",
        effort="low",
        plugin_dir=Path("."),
        repo_root=REPO_ROOT,
        fixture_dir=Path("."),
        artifact_dir=Path("."),
        desktop_supervisor=Path("/usr/bin/true"),
        desktop_python=Path("/usr/bin/true"),
        claude_config_dir=None,
        timeout_s=5,
        max_budget_usd=None,
        append_system_prompt="test",
        allow_bash=not adapter_args.no_bash,
    )
    argv = adapter.build_claude_command(
        mcp_config=Path("mcp.json"), strict_mcp_config=True, mcp_allowed_tools=""
    )
    denied = {
        tool
        for index, value in enumerate(argv)
        if value == "--disallowedTools"
        for tool in argv[index + 1].split(",")
    }

    assert ("Bash" in denied) is bash_withheld


def test_the_live_entrypoint_defaults_to_the_smoke_tier_not_every_package() -> None:
    """Omitting --scenario must not drive the core tier through a live session.

    This entrypoint spends model tokens against an authenticated Claude Code
    session. Before the tier boundary existed, "default: all" meant the two
    smoke packages; adding core packages to the same root silently made it
    mean those too -- including one that needs a Docker Postgres and one whose
    evidence a live run cannot produce. The runner CLI's boundary did not
    cover this second loader call site.
    """

    module = _load_runner_module()
    args = module.build_parser().parse_args([])
    assert args.tier == "smoke"
    assert args.scenario == []

    scenarios = load_scenarios(SCENARIO_ROOT)
    in_scope = module._scenarios_in_scope(scenarios, args.scenario, args.tier)
    assert {scenario.id for scenario in in_scope} == {
        scenario.id for scenario in scenarios if scenario.tier == "smoke"
    }
    assert all(scenario.tier == "smoke" for scenario in in_scope)
    assert len(in_scope) < len(scenarios), "the boundary excluded nothing"


def test_the_live_entrypoint_still_lets_an_explicit_id_cross_the_tier() -> None:
    """Naming a core scenario is the deliberate way to run one live."""

    module = _load_runner_module()
    args = module.build_parser().parse_args(["--scenario", "credential-rotation"])
    assert args.scenario == ["credential-rotation"]

    scenarios = load_scenarios(SCENARIO_ROOT)
    in_scope = module._scenarios_in_scope(scenarios, args.scenario, args.tier)
    assert {scenario.id for scenario in in_scope} == {scenario.id for scenario in scenarios}


# ---------------------------------------------------------------------------
# The driver flags
#
# Every test below runs with aiohttp and raw sockets replaced by functions
# that raise, so a provider call that escapes the fake fails loudly instead of
# reaching the network.
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _no_network(monkeypatch: pytest.MonkeyPatch) -> None:
    import socket

    import aiohttp

    def refuse(*args: object, **kwargs: object) -> None:
        raise AssertionError("test attempted a real network call")

    monkeypatch.setattr(aiohttp, "ClientSession", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)


def _driver_args(module, argv: list[str]):
    return module.build_parser().parse_args(argv)


def _driver_scenario(scenario_id: str = "driver-cli", *, turns: int = 2):
    """A scenario whose answer sheet declares the driver's forbidden vocabulary."""

    from dp_scenarios.operator.answer_sheet import answer_sheet_from_mapping
    from dp_scenarios.operator.engine import OperatorScript
    from dp_scenarios.operator.persona import load_persona
    from dp_scenarios.scenario import FixtureSpec
    from dp_scenarios.grading.statistics import RepeatabilityTier as _Tier

    from test_runner_tier import FakeScenario, ROOT

    opening = "Improve visibility."
    messages = [opening, *[f"Please continue {index}." for index in range(1, turns)]]
    sheet = answer_sheet_from_mapping(
        {
            "version": 1,
            "scenario_id": scenario_id,
            "opening_message": opening,
            "turns": messages,
            "source_answers": {"source": "Use the source."},
            "decision_answers": {"choice": {"terms": ["choice"], "answer": "Yes."}},
            "status_answers": {"status": "Ready."},
            "ground_truth": {"infra": {"terms": ["source"], "fact": "The source is a nightly export."}},
            "driver_forbidden_terms": ["late delivery rate"],
            "opening_forbidden_terms": ["source"],
            "open_decision_markers": ["[DECISION NEEDED]"],
            "obstacle_terms": [],
        }
    )
    persona = load_persona(ROOT / "scenarios/_personas/smoke.yaml")
    script = OperatorScript.from_components(
        persona,
        sheet,
        turns=sheet.turns,
        turn_budget=turns,
        phase_by_turn={index: min(index, 7) for index in range(1, turns + 1)},
    )
    return FakeScenario(
        scenario_id,
        "smoke",
        FixtureSpec("zero_row_optional", 29, "file-backed"),
        turns,
        script,
        1,
        _Tier.DEMONSTRATED_ONCE,
    )


def test_driver_flags_default_to_a_scripted_operator() -> None:
    module = _load_runner_module()
    args = _driver_args(module, [])

    assert args.driver_model is None
    # 1.0 is the API default and the only value GPT-5-class models accept; at
    # that value the field is omitted from the request entirely, so one default
    # works for both model generations. Defaulting to 0.7 meant the documented
    # flow against a current model was a guaranteed 400 on every authorable
    # turn -- which degrades to a silent fallback, not an error.
    assert args.driver_temperature == 1.0
    assert args.driver_timeout == 60.0
    assert args.driver_max_tokens == 400


def test_driver_configuration_is_the_identity_without_the_flag() -> None:
    from dp_scenarios.runner.environment import PinnedVersions

    module = _load_runner_module()
    scripted = PinnedVersions("skills-1", "supervisor-1", "wheel-1", "mock-1", "claims-1")

    result_pins, factory = module.driver_configuration(_driver_args(module, []), scripted)

    assert result_pins is scripted
    assert factory is None
    assert result_pins.driver_model_id == "not-applicable"
    assert dict(result_pins.driver_sampling_params) == {}


def test_driver_configuration_refuses_before_anything_is_spent_without_the_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from dp_scenarios.operator.openai_driver import DriverConfigError
    from dp_scenarios.runner.environment import PinnedVersions

    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    module = _load_runner_module()
    args = _driver_args(module, ["--driver-model", "m"])

    with pytest.raises(DriverConfigError, match="OPENAI_API_KEY is not set in the environment"):
        module.driver_configuration(args, PinnedVersions("s", "v", "w", "mock-1", "c"))


def test_driver_configuration_pins_the_model_temperature_and_prompt_hash(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from dp_scenarios.operator.driver import DriverOperator
    from dp_scenarios.operator.openai_driver import driver_prompt_hash
    from dp_scenarios.runner.environment import PinnedVersions

    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    module = _load_runner_module()
    args = _driver_args(module, ["--driver-model", "m", "--driver-temperature", "0.2", "--driver-timeout", "5"])

    driver_pins, factory = module.driver_configuration(args, PinnedVersions("s", "v", "w", "mock-1", "c"))

    assert driver_pins.driver_model_id == "m"
    # max_tokens is pinned for the same reason as the prompt hash: on
    # GPT-5-class models the cap spans reasoning tokens, so it decides whether a
    # turn produces text at all, and two runs differing by it are two different
    # operators.
    assert dict(driver_pins.driver_sampling_params) == {
        "temperature": 0.2,
        "max_tokens": 400,
        "prompt_hash": driver_prompt_hash(),
    }
    assert factory is not None
    operator = factory(object(), object(), 1)
    assert isinstance(operator, DriverOperator)
    assert operator.model_id == "m"
    assert operator.temperature == 0.2
    assert operator.provider_timeout_seconds == 5.0
    # The pins and the surface must agree by construction, not by convention.
    assert operator.model_id == driver_pins.driver_model_id
    assert float(driver_pins.driver_sampling_params["temperature"]) == operator.temperature


def test_driver_configuration_never_lets_the_key_reach_the_pins_or_the_operator(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from dp_scenarios.runner.environment import PinnedVersions

    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    module = _load_runner_module()
    args = _driver_args(module, ["--driver-model", "m"])

    driver_pins, factory = module.driver_configuration(args, PinnedVersions("s", "v", "w", "mock-1", "c"))
    operator = factory(object(), object(), 1)

    for text in (repr(driver_pins), str(dict(driver_pins.driver_sampling_params)), repr(operator), str(operator)):
        assert "sk-test" not in text
        assert "Bearer" not in text


def test_driver_configuration_authors_a_turn_through_the_real_provider_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The factory's product must actually reach the OpenAI transport seam."""

    from dp_scenarios.operator import openai_driver
    from dp_scenarios.operator.driver import DriverView
    from dp_scenarios.runner.environment import PinnedVersions

    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    seen: dict[str, object] = {}

    def fake_post(url: str, headers, body, timeout: float):
        seen.update(url=url, headers=dict(headers), body=dict(body), timeout=timeout)
        return {"choices": [{"message": {"content": "The nightly export is the source."}}]}

    monkeypatch.setattr(openai_driver, "_aiohttp_post", fake_post)
    module = _load_runner_module()
    args = _driver_args(module, ["--driver-model", "m", "--driver-temperature", "0.25", "--driver-timeout", "8"])
    _, factory = module.driver_configuration(args, PinnedVersions("s", "v", "w", "mock-1", "c"))

    view = DriverView(
        turn=2,
        phase=1,
        persona_id="p",
        persona_label="Operator",
        persona_vocabulary=(),
        persona_behaviors=(),
        agent_message="Where does the data come from?",
        selected_reply="A nightly export.",
        prior_operator_messages=(),
        remaining_turns=3,
        prior_agent_messages=(),
        known_facts=(("infra", "The source is a nightly export."),),
        facts_already_stated=(),
        beat=None,
        forbidden_terms=("late delivery rate",),
        rejection_notice=None,
    )
    render = factory(object(), object(), 1).author(view, fallback="fallback", check=lambda text: None)

    assert render.text == "The nightly export is the source."
    assert render.used_fallback is False
    assert seen["url"].endswith("/chat/completions")
    assert seen["headers"]["Authorization"] == "Bearer sk-test"
    assert seen["body"]["model"] == "m"
    assert seen["body"]["temperature"] == 0.25
    assert seen["timeout"] == 8.0


def _fake_post_returning(text: str):
    def fake_post(url: str, headers, body, timeout: float):
        return {"choices": [{"message": {"content": text}}]}

    return fake_post


@pytest.mark.parametrize("branch", ["replay", "session"])
def test_driver_configuration_output_passes_the_tier_consistency_gate(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    branch: str,
) -> None:
    """The helper's pins and factory must agree end to end, on both branches."""

    from dp_scenarios.operator import openai_driver
    from dp_scenarios.operator.transport import TurnResult
    from dp_scenarios.runner.environment import PinnedVersions
    from dp_scenarios.runner.session import LiveSession
    from dp_scenarios.runner.tier import TierRunner

    from test_runner_tier import clean_canary, recording_for, responses_for

    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setattr(openai_driver, "_aiohttp_post", _fake_post_returning("Carry on."))
    module = _load_runner_module()
    args = _driver_args(module, ["--driver-model", "m", "--driver-temperature", "0.0"])
    driver_pins, factory = module.driver_configuration(
        args, PinnedVersions("skills-1", "supervisor-1", "wheel-1", "mock-1", "claims-1")
    )
    scenario = _driver_scenario(f"driver-gate-{branch}")

    kwargs: dict[str, object] = {}
    if branch == "replay":
        # Record through the driver, not the scripted engine: the operator's
        # words on a substitutable turn are the driver's, so a scripted
        # recording would mismatch a driven rerun.
        kwargs["replay_recordings"] = {
            scenario.id: recording_for(scenario, responses_for(scenario), driver=factory(scenario, None, 0))
        }
    else:
        responses = iter([TurnResult(agent_message="What is the source?") for _ in scenario.script.turns])
        kwargs["session_factory"] = lambda *_: LiveSession(handler=lambda message: next(responses))

    result = TierRunner(
        [scenario],
        pins=driver_pins,
        canary=clean_canary(),
        environment_root=tmp_path / branch,
        evidence_root=tmp_path / branch / "evidence",
        operator_factory=factory,
        **kwargs,
    ).run()

    run = result.scenario_runs[0]
    # Two independent claims, asserted separately on purpose: a disjunction
    # here would pass on either half and prove neither.
    assert run.qualification.operator_mode == "driver"
    assert run.replay_verification_status == "not-attempted"
    assert run.replay_verification_reason == "driver operator output is not assumed deterministic"
    qualification = json.loads((Path(run.evidence_bundle_dir) / "qualification.json").read_text(encoding="utf-8"))
    assert qualification["operator_mode"] == "driver"
    assert qualification["replay_status"] == "not-attempted"
    manifest = json.loads((Path(run.evidence_bundle_dir) / "manifest.json").read_text(encoding="utf-8"))
    assert "sk-test" not in json.dumps(manifest)


@pytest.mark.parametrize("branch", ["replay", "session"])
def test_tier_refuses_the_helpers_factory_against_scripted_pins(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    branch: str,
) -> None:
    """Dropping the pins half of the helper must abort the run, not record it."""

    from dp_scenarios.operator import openai_driver
    from dp_scenarios.operator.transport import TurnResult
    from dp_scenarios.runner.environment import PinnedVersions
    from dp_scenarios.runner.session import LiveSession
    from dp_scenarios.runner.tier import TierRunner

    from test_runner_tier import clean_canary, recording_for, responses_for

    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setattr(openai_driver, "_aiohttp_post", _fake_post_returning("Carry on."))
    module = _load_runner_module()
    scripted = PinnedVersions("skills-1", "supervisor-1", "wheel-1", "mock-1", "claims-1")
    args = _driver_args(module, ["--driver-model", "m", "--driver-temperature", "0.0"])
    _, factory = module.driver_configuration(args, scripted)
    scenario = _driver_scenario(f"driver-na-{branch}")
    root = tmp_path / branch
    root.mkdir()

    kwargs: dict[str, object] = {}
    if branch == "replay":
        kwargs["replay_recordings"] = {scenario.id: recording_for(scenario, responses_for(scenario))}
    else:
        responses = iter([TurnResult(agent_message="What is the source?") for _ in scenario.script.turns])
        kwargs["session_factory"] = lambda *_: LiveSession(handler=lambda message: next(responses))

    with pytest.raises(TierError, match="manifest driver pins and operator factory disagree"):
        TierRunner(
            [scenario],
            pins=scripted,  # the driver pins were dropped
            canary=clean_canary(),
            environment_root=root,
            operator_factory=factory,
            **kwargs,
        ).run()


def test_tier_refuses_driver_pins_without_a_factory_before_any_session_starts(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from dp_scenarios.runner.environment import PinnedVersions
    from dp_scenarios.runner.tier import TierRunner

    from test_runner_tier import clean_canary

    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    module = _load_runner_module()
    args = _driver_args(module, ["--driver-model", "m", "--driver-temperature", "0.0"])
    driver_pins, _ = module.driver_configuration(
        args, PinnedVersions("skills-1", "supervisor-1", "wheel-1", "mock-1", "claims-1")
    )
    scenario = _driver_scenario("driver-no-factory")
    started: list[str] = []
    generated: list[str] = []

    # The preflight's whole point is that it fires before an environment is
    # entered.  The per-epoch consistency gate would also raise here, so the
    # exception alone proves nothing; what separates the two is whether the
    # scenario's fixture was generated first.
    class WatchedScenario(type(scenario)):  # type: ignore[misc]
        def generate_fixture(self, out_dir):  # type: ignore[no-untyped-def]
            generated.append(str(out_dir))
            return super().generate_fixture(out_dir)

    watched = WatchedScenario(**{
        field: getattr(scenario, field) for field in scenario.__dataclass_fields__
    })

    def session_factory(*args: object) -> object:
        started.append("constructed")
        raise AssertionError("no session may start when the pins cannot be honoured")

    with pytest.raises(TierError, match="manifest driver pins require an operator factory"):
        TierRunner(
            [watched],
            pins=driver_pins,
            canary=clean_canary(),
            environment_root=tmp_path,
            session_factory=session_factory,
            operator_factory=None,
        ).run()
    assert started == []
    assert generated == []
    assert list(tmp_path.iterdir()) == []


def test_tier_refuses_a_driver_whose_model_or_temperature_differs_from_the_pins(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from dp_scenarios.operator import openai_driver
    from dp_scenarios.operator.driver import DriverOperator
    from dp_scenarios.runner.environment import PinnedVersions
    from dp_scenarios.runner.tier import TierRunner

    from test_runner_tier import clean_canary, recording_for, responses_for

    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setattr(openai_driver, "_aiohttp_post", _fake_post_returning("Carry on."))
    module = _load_runner_module()
    args = _driver_args(module, ["--driver-model", "m", "--driver-temperature", "0.0"])
    driver_pins, factory = module.driver_configuration(
        args, PinnedVersions("skills-1", "supervisor-1", "wheel-1", "mock-1", "claims-1")
    )
    scenario = _driver_scenario("driver-mismatch")
    recording = recording_for(scenario, responses_for(scenario))
    product = factory(object(), object(), 1)

    for index, wrong in enumerate(
        (
            DriverOperator(product.provider, model_id="other-model", temperature=0.0),
            DriverOperator(product.provider, model_id="m", temperature=0.9),
        )
    ):
        root = tmp_path / f"case-{index}"
        root.mkdir()
        with pytest.raises(TierError, match="manifest driver pins and operator factory disagree"):
            TierRunner(
                [scenario],
                pins=driver_pins,
                canary=clean_canary(),
                environment_root=root,
                replay_recordings={scenario.id: recording},
                operator_factory=lambda *_: wrong,
            ).run()


@pytest.mark.parametrize("temperature", ["hot", None, True])
def test_tier_refuses_pins_whose_temperature_is_not_a_number(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    temperature: object,
) -> None:
    """A pinned temperature that is not a number cannot be compared to one.

    ``True`` is included on purpose: ``isinstance(True, int)`` is true in
    Python, so a bare numeric check would compare a boolean against 1.0 and
    silently accept a driver running at temperature 1.
    """

    from dataclasses import replace as dataclass_replace

    from dp_scenarios.ledger.manifest import ManifestError
    from dp_scenarios.operator.driver import DriverOperator
    from dp_scenarios.runner.environment import PinnedVersions
    from dp_scenarios.runner.tier import TierRunner

    from test_runner_tier import clean_canary, recording_for, responses_for

    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    scripted = PinnedVersions("skills-1", "supervisor-1", "wheel-1", "mock-1", "claims-1")
    bad_pins = dataclass_replace(
        scripted, driver_model_id="m", driver_sampling_params={"temperature": temperature}
    )
    scenario = _driver_scenario("driver-bad-temperature")
    driver = DriverOperator(lambda view: "Carry on.", model_id="m", temperature=1.0)
    root = tmp_path / str(temperature)
    root.mkdir()

    # The manifest owns this refusal: pins carrying a non-numeric temperature
    # are malformed on their own terms, whatever factory accompanies them, so
    # they are rejected when the run environment is built -- ahead of the
    # per-epoch gate that cross-checks the pins against the factory.  Either
    # refusal is acceptable to this test; silently accepting one is not.  The
    # ``True`` case still bites: drop the bool guard and float(True) == 1.0
    # matches the driver's own temperature, so nothing downstream complains.
    with pytest.raises((TierError, ManifestError), match="temperature must be a number between 0 and 2"):
        TierRunner(
            [scenario],
            pins=bad_pins,
            canary=clean_canary(),
            environment_root=root,
            replay_recordings={scenario.id: recording_for(scenario, responses_for(scenario), driver=driver)},
            operator_factory=driver,
        ).run()


def test_a_token_and_host_home_bash_are_refused_rather_than_silently_resolved() -> None:
    """`CLAUDE_CODE_OAUTH_TOKEN` is commonly exported, so this is easy to hit.

    Withholding Bash silently made every shell-dependent scenario fail for a
    reason that appeared nowhere in the report.
    """

    import argparse

    module = _load_runner_module()
    args = argparse.Namespace(allow_host_home=True, allow_host_home_bash=True)
    with pytest.raises(TierError, match="cannot be combined with a Claude OAuth token"):
        module._tool_grant_arguments(args, oauth_token_present=True)

    # Without the flag the token still withholds Bash, which is the intent.
    quiet = argparse.Namespace(allow_host_home=True, allow_host_home_bash=False)
    assert module._tool_grant_arguments(quiet, oauth_token_present=True) == ["--no-bash"]
    assert module._tool_grant_arguments(quiet, oauth_token_present=False) == ["--no-bash"]

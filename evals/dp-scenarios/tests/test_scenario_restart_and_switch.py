"""Guard tests for the core-tier restart-and-switch scenario.

These tests exercise the declarative package (``scenario.yaml`` and friends)
and the mechanical follow-up grading in
``dp_scenarios.followups.restart_and_switch.check`` against evidence shaped
like what a real attempt-keyed broker restart and a real post-restart
workflow-switch call would produce.

Two evidence sources are used. The mutation-tested section below builds
target mappings by hand, the same pattern ``credential-rotation`` and
``sigterm-diagnosis`` use for their own follow-up checks. The section after it
does *not* hand-write evidence: it drives ``dp_scenarios.knobs.broker``'s real
process-level shim through a real subprocess and two real, disposable mock
HTTP servers through
``dp_scenarios.knobs.workflow.script_restart_and_switch``, feeding their
*actual* output into ``SCENARIO.follow_up_check``. No live agent session and
no live supervisor build are started anywhere in this file; see the scenario
README for what that is, and is not, coverage of.
"""

from __future__ import annotations

import json
import shutil
import socket
import subprocess
import sys
import urllib.request
from pathlib import Path

import pytest

from dp_scenarios.knobs import (
    BrokerFaultPlan,
    BrokerFaultShape,
    EndpointObservation,
    WorkflowSwitchPlan,
    broker_entrypoint_path,
    script_restart_and_switch,
)
from dp_scenarios.mockrest.config import load_config
from dp_scenarios.operator import EventType
from dp_scenarios.runner.environment import MockSourceHandle
from dp_scenarios.scenario import load_scenario


ROOT = Path(__file__).parents[1]
SCENARIO = load_scenario(ROOT / "scenarios/restart-and-switch")
GOLD = json.loads(SCENARIO.gold["oracle"].read_text(encoding="utf-8"))


# --------------------------------------------------------------------------
# Package wiring
# --------------------------------------------------------------------------


def test_scenario_declares_the_core_tier() -> None:
    assert SCENARIO.tier == "core"
    assert SCENARIO.run_order == 5
    assert SCENARIO.dataset == "grain_trap"
    assert SCENARIO.seed == 29


def test_gold_endpoint_identities_match_the_fixture_that_actually_serves_them() -> None:
    """Pin the endpoint identities against the servers, not against the gold.

    ``stale_endpoint``/``new_endpoint`` are what the check compares a
    reported ``answered_endpoint`` against, so a test that reads them from the
    gold cannot notice them drifting. These literals are the ones
    ``_OLD_CONFIG``/``_NEW_CONFIG`` below actually serve on the real
    mock-server arm; if the gold moves away from them, the drill grades an
    endpoint nothing in the fixture ever answers with.
    """

    assert GOLD["stale_endpoint"] == "endpoint-v1"
    assert GOLD["new_endpoint"] == "endpoint-v2"
    assert _OLD_CONFIG.routes[0].response.data["endpoint"] == GOLD["stale_endpoint"]
    assert _NEW_CONFIG.routes[0].response.data["endpoint"] == GOLD["new_endpoint"]


def test_gates_wire_the_restart_and_switch_follow_up() -> None:
    binding = SCENARIO.gates["follow-up"]
    assert binding.kind == "restart_and_switch"
    assert binding.settings["true_classification"] == "serving_down"


def test_turn_one_is_one_sentence_without_mechanism_nouns() -> None:
    ask = SCENARIO.answer_sheet.turn_one
    forbidden = set(SCENARIO.answer_sheet.opening_forbidden_terms)
    lowered = ask.casefold()
    assert sum(character in ".!?" for character in ask) == 1
    assert not any(term in lowered for term in forbidden)
    for term in ("restart", "bind", "port", "workflow", "broken", "retry"):
        assert term in forbidden


def test_the_rebuild_bait_event_offers_the_wrong_remedy_without_encoding_it() -> None:
    """The scripted operator turn bait ("tear it down and rebuild from
    scratch") mirrors an over-eager full-rebuild response to a transient bind
    failure -- the trap this drill exists to catch -- without itself
    determining what the follow-up check requires.
    """

    misdiagnosis_cards = [
        card for card in SCENARIO.events.cards if card.event_type is EventType.MISDIAGNOSIS
    ]
    assert len(misdiagnosis_cards) == 1
    card = misdiagnosis_cards[0]
    assert card.plant is False
    assert card.card_id not in SCENARIO.required_plants


def test_scenario_has_no_scoreable_answer_gold() -> None:
    # The pass criteria are connection-level (bind-failure classification,
    # no-stderr reproducibility, retry discipline, post-restart endpoint
    # identity), not a served semantic query row-set, so this scenario
    # certifies only the build gate -- the same pattern credential-rotation
    # and sigterm-diagnosis use for the same reason.
    assert not SCENARIO.has_scoreable_answer_gold
    assert SCENARIO.repeatability.gates == ("build",)


# --------------------------------------------------------------------------
# Mutation-tested mechanical grading (hand-written evidence)
# --------------------------------------------------------------------------


def _clean_target() -> dict[str, object]:
    return {
        "attempts": {
            "1": {
                "fault": "occupied_port",
                "outcome": "bind_failed",
                "stderr": "",
                "evidence_ref": "serve-phase/attempt-1/bind",
            },
            "2": {
                "fault": "none",
                "outcome": "served",
                "stderr": "",
                "evidence_ref": "serve-phase/attempt-2/bind",
            },
        },
        "diagnosis": {
            "attempt_classifications": {"1": "serving_down"},
            "build_status_claim": "healthy",
            "build_status_evidence_ref": None,
            "retry_strategy": "scripted_restart_once",
        },
        "phase_evidence": {
            "bind_failure_diagnosed_turn": 4,
            "restart_turn": 5,
            "switch_turn": 6,
        },
        "workflow_switch": {
            "from_workflow": "orders-workflow-v1",
            "to_workflow": "orders-workflow-v2",
            "answered_workflow": "orders-workflow-v2",
            "answered_endpoint": "endpoint-v2",
            "stale_endpoint_rejected": True,
        },
    }


def test_clean_evidence_passes_every_check() -> None:
    result = SCENARIO.follow_up_check(_clean_target())
    assert result == {"status": "examined", "passed": True, "findings": []}


def test_missing_evidence_is_not_examined_not_a_pass() -> None:
    assert SCENARIO.follow_up_check({}) == {
        "status": "not-examined",
        "passed": False,
        "findings": ["attempts_not_examined"],
    }
    assert SCENARIO.follow_up_check("not-a-mapping") == {
        "status": "not-examined",
        "passed": False,
        "findings": ["restart_and_switch_not_examined"],
    }
    assert SCENARIO.follow_up_check({"attempts": {"x": {}}}) == {
        "status": "not-examined",
        "passed": False,
        "findings": ["attempts_not_examined"],
    }
    assert SCENARIO.follow_up_check({"attempts": {"1": "not-a-mapping"}}) == {
        "status": "not-examined",
        "passed": False,
        "findings": ["attempts_not_examined"],
    }


def test_a_third_attempt_beyond_the_declared_plan_is_retry_until_lucky() -> None:
    target = _clean_target()
    target["attempts"]["3"] = {
        "fault": "none",
        "outcome": "served",
        "stderr": "",
        "evidence_ref": "serve-phase/attempt-3/bind",
    }
    result = SCENARIO.follow_up_check(target)
    assert not result["passed"]
    assert "attempt_count_disagrees_with_plan" in result["findings"]


def test_a_dropped_cleared_attempt_disagrees_with_the_plan() -> None:
    target = _clean_target()
    del target["attempts"]["2"]
    result = SCENARIO.follow_up_check(target)
    assert not result["passed"]
    assert "attempt_count_disagrees_with_plan" in result["findings"]


def test_a_fault_declared_on_the_wrong_attempt_is_caught() -> None:
    target = _clean_target()
    target["attempts"]["1"]["fault"] = "none"
    result = SCENARIO.follow_up_check(target)
    assert not result["passed"]
    assert "attempt_fault_disagrees_with_plan:1" in result["findings"]


def test_leaked_stderr_on_the_faulted_attempt_is_caught() -> None:
    target = _clean_target()
    target["attempts"]["1"]["stderr"] = "Traceback (most recent call last):\n"
    result = SCENARIO.follow_up_check(target)
    assert not result["passed"]
    assert "attempt_leaked_stderr:1" in result["findings"]


def test_a_build_phase_evidence_ref_for_a_bind_attempt_is_caught() -> None:
    """A bind attempt is always serve-phase evidence: what happened when the
    process tried to bind and serve, never a claim about the build.
    """

    target = _clean_target()
    target["attempts"]["1"]["evidence_ref"] = "build-phase/attempt-1/compile-log"
    result = SCENARIO.follow_up_check(target)
    assert not result["passed"]
    assert "attempt_evidence_ref_not_serve_phase:1" in result["findings"]


def test_a_faulted_attempt_that_claims_it_served_anyway_is_caught() -> None:
    target = _clean_target()
    target["attempts"]["1"]["outcome"] = "served"
    result = SCENARIO.follow_up_check(target)
    assert not result["passed"]
    assert "faulted_attempt_did_not_fail_to_bind:1" in result["findings"]


def test_a_cleared_attempt_that_claims_it_failed_to_bind_is_caught() -> None:
    target = _clean_target()
    target["attempts"]["2"]["outcome"] = "bind_failed"
    result = SCENARIO.follow_up_check(target)
    assert not result["passed"]
    assert "cleared_attempt_did_not_serve:2" in result["findings"]


def test_classifying_the_bind_failure_as_a_broken_build_is_rejected() -> None:
    """The exact misattribution this drill exists to catch: a transient,
    attempt-scoped bind failure reported as the build being broken.
    """

    target = _clean_target()
    target["diagnosis"]["attempt_classifications"]["1"] = "build_broken"
    result = SCENARIO.follow_up_check(target)
    assert not result["passed"]
    assert "attempt_misclassified:build_broken" in result["findings"]


@pytest.mark.parametrize("wrong", ["build_broken", "code_defect", "deployment_broken", "unknown"])
def test_every_documented_wrong_classification_is_rejected(wrong: str) -> None:
    target = _clean_target()
    target["diagnosis"]["attempt_classifications"]["1"] = wrong
    result = SCENARIO.follow_up_check(target)
    assert not result["passed"]
    assert f"attempt_misclassified:{wrong}" in result["findings"]


def test_an_unhealthy_build_claim_backed_by_serve_phase_evidence_is_rejected() -> None:
    """The core trap: citing the serve-phase bind-failure evidence to back a
    claim that the build itself is unhealthy.
    """

    target = _clean_target()
    target["diagnosis"]["build_status_claim"] = "unhealthy"
    target["diagnosis"]["build_status_evidence_ref"] = "serve-phase/attempt-1/bind"
    result = SCENARIO.follow_up_check(target)
    assert not result["passed"]
    assert "unhealthy_claim_not_backed_by_build_phase_evidence" in result["findings"]


def test_an_unhealthy_build_claim_backed_by_build_phase_evidence_is_accepted() -> None:
    """The inverse of the above: an unhealthy-build claim is not rejected
    outright, only one backed by the wrong evidence phase.
    """

    target = _clean_target()
    target["diagnosis"]["build_status_claim"] = "unhealthy"
    target["diagnosis"]["build_status_evidence_ref"] = "build-phase/attempt-1/compile-log"
    result = SCENARIO.follow_up_check(target)
    assert result["passed"], result["findings"]


def test_an_unhealthy_claim_with_no_evidence_ref_at_all_is_rejected() -> None:
    target = _clean_target()
    target["diagnosis"]["build_status_claim"] = "unhealthy"
    target["diagnosis"]["build_status_evidence_ref"] = None
    result = SCENARIO.follow_up_check(target)
    assert not result["passed"]
    assert "unhealthy_claim_not_backed_by_build_phase_evidence" in result["findings"]


@pytest.mark.parametrize(
    "strategy", ["retry_until_bound_free", "poll_until_port_free", "rebuild_from_scratch"]
)
def test_a_retry_until_lucky_strategy_name_is_rejected(strategy: str) -> None:
    target = _clean_target()
    target["diagnosis"]["retry_strategy"] = strategy
    result = SCENARIO.follow_up_check(target)
    assert not result["passed"]
    assert f"retry_until_lucky_detected:{strategy}" in result["findings"]


def test_diagnosis_after_the_restart_already_happened_is_caught() -> None:
    target = _clean_target()
    target["phase_evidence"]["bind_failure_diagnosed_turn"] = 6
    target["phase_evidence"]["restart_turn"] = 5
    result = SCENARIO.follow_up_check(target)
    assert not result["passed"]
    assert "restart_attempted_before_diagnosis" in result["findings"]


def test_a_switch_call_recorded_before_the_restart_is_caught() -> None:
    target = _clean_target()
    target["phase_evidence"]["switch_turn"] = 4
    result = SCENARIO.follow_up_check(target)
    assert not result["passed"]
    assert "switch_call_before_restart" in result["findings"]


def test_a_post_switch_call_still_answered_by_the_old_workflow_is_caught() -> None:
    target = _clean_target()
    target["workflow_switch"]["answered_workflow"] = "orders-workflow-v1"
    result = SCENARIO.follow_up_check(target)
    assert not result["passed"]
    assert "post_switch_call_served_by_wrong_workflow" in result["findings"]


def test_an_unconfirmed_stale_endpoint_rejection_is_caught() -> None:
    target = _clean_target()
    target["workflow_switch"]["stale_endpoint_rejected"] = False
    result = SCENARIO.follow_up_check(target)
    assert not result["passed"]
    assert "stale_endpoint_not_confirmed_rejected" in result["findings"]


def test_a_workflow_pair_that_disagrees_with_the_oracle_is_caught() -> None:
    target = _clean_target()
    target["workflow_switch"]["to_workflow"] = "some-other-workflow"
    result = SCENARIO.follow_up_check(target)
    assert not result["passed"]
    assert "workflow_switch_disagrees_with_oracle" in result["findings"]


def _scenario_with_oracle(tmp_path: Path, oracle: object) -> object:
    """Load a real copy of the scenario package with a mutated oracle gold.

    The guards that turn an unreadable or malformed oracle into a failure --
    rather than silently skipping the whole per-attempt reconciliation block --
    are only reachable through the gold file itself, so they need a real
    package on disk rather than a mutated target mapping.
    """

    # The package references shared sibling directories (personas, examples)
    # by relative path, so the copy has to preserve that layout.
    for sibling in ("_personas", "_examples"):
        shutil.copytree(ROOT / "scenarios" / sibling, tmp_path / sibling)
    package = tmp_path / "restart-and-switch"
    shutil.copytree(ROOT / "scenarios/restart-and-switch", package)
    (package / "gold/restart_and_switch_oracle.json").write_text(
        json.dumps(oracle), encoding="utf-8"
    )
    return load_scenario(package)


def test_a_non_mapping_oracle_fails_rather_than_skipping_reconciliation(tmp_path: Path) -> None:
    scenario = _scenario_with_oracle(tmp_path, ["not", "a", "mapping"])
    result = scenario.follow_up_check(_clean_target())
    assert result["status"] == "ungraded"
    assert not result["passed"]
    assert "oracle_gold_unreadable" in result["findings"]
    assert "attempts_not_reconciled_against_oracle" not in result["findings"]


@pytest.mark.parametrize(
    "mutation",
    [
        {"fault_attempt": 0},
        {"cleared_attempt": "two"},
        {"max_attempts": None},
        {"fault_shape": 17},
    ],
    ids=["fault_attempt", "cleared_attempt", "max_attempts", "fault_shape"],
)
def test_a_malformed_oracle_field_fails_rather_than_skipping_reconciliation(
    tmp_path: Path, mutation: dict[str, object]
) -> None:
    result = _scenario_with_oracle(tmp_path, {**GOLD, **mutation}).follow_up_check(_clean_target())
    assert result["status"] == "ungraded"
    assert not result["passed"]
    assert "oracle_gold_malformed" in result["findings"]
    assert "attempts_not_reconciled_against_oracle" not in result["findings"]


def test_an_unknown_fault_shape_fails_rather_than_skipping_reconciliation(tmp_path: Path) -> None:
    # Reaches the BrokerFaultShape/BrokerFaultPlan construction guard: the
    # name is a string, so the field-level check above passes it through.
    result = _scenario_with_oracle(
        tmp_path, {**GOLD, "fault_shape": "no-such-shape"}
    ).follow_up_check(_clean_target())
    assert result["status"] == "ungraded"
    assert not result["passed"]
    assert "oracle_gold_malformed" in result["findings"]
    assert "attempts_not_reconciled_against_oracle" not in result["findings"]


def test_an_unreadable_oracle_is_ungraded_without_a_fake_reconciliation_failure(
    tmp_path: Path,
) -> None:
    """An unusable oracle voids the reconciliation without inventing a code.

    The per-attempt checks need a valid oracle schedule. The gold finding is
    therefore the truthful diagnosis; the old ``attempts_not_reconciled``
    fallback was unreachable and claimed a comparison that never happened.
    """

    scenario = _scenario_with_oracle(tmp_path, ["unreadable"])
    target = _clean_target()
    # Evidence that would fail the per-attempt checks if a valid oracle made
    # those checks possible. It must not manufacture a reconciliation code
    # when the oracle itself is unreadable.
    target["attempts"]["1"]["fault"] = "not-the-planted-shape"
    target["attempts"]["1"]["stderr"] = "a leaked diagnostic"
    target["attempts"]["1"]["evidence_ref"] = "build-phase/attempt-1/bind"
    result = scenario.follow_up_check(target)
    assert result["status"] == "ungraded"
    assert not result["passed"]
    assert "oracle_gold_unreadable" in result["findings"]
    assert "attempts_not_reconciled_against_oracle" not in result["findings"]


@pytest.mark.parametrize(
    ("path", "value", "expected"),
    [
        (("attempts", "1", "stderr"), 17, "attempt_evidence_not_examined:1"),
        (("attempts", "1", "evidence_ref"), None, "attempt_evidence_ref_not_serve_phase:1"),
        (("diagnosis", "attempt_classifications"), None, "attempt_classification_not_examined"),
        (("diagnosis", "attempt_classifications"), {}, "attempt_classification_not_examined"),
        (("diagnosis", "attempt_classifications"), {"1": "   "}, "attempt_classification_not_examined"),
        (("diagnosis", "build_status_claim"), None, "build_status_claim_not_examined"),
        (("diagnosis", "build_status_claim"), "probably fine", "build_status_claim_not_examined"),
        (("diagnosis", "retry_strategy"), None, "retry_strategy_not_examined"),
        (("diagnosis", "retry_strategy"), "  ", "retry_strategy_not_examined"),
        (("phase_evidence", "restart_turn"), "5", "phase_evidence_not_examined"),
        (("phase_evidence", "switch_turn"), True, "phase_evidence_not_examined"),
        (("phase_evidence", "bind_failure_diagnosed_turn"), None, "phase_evidence_not_examined"),
        (("workflow_switch", "answered_endpoint"), "", "workflow_switch_endpoint_not_examined"),
        (("workflow_switch", "answered_endpoint"), 12, "workflow_switch_endpoint_not_examined"),
        (("workflow_switch", "answered_workflow"), None, "post_switch_call_served_by_wrong_workflow"),
    ],
)
def test_a_malformed_field_is_not_examined_never_a_silent_pass(
    path: tuple[str, ...], value: object, expected: str
) -> None:
    """Field-level malformation, not whole-sub-mapping deletion.

    Deleting ``diagnosis`` wholesale is already covered below; these pin the
    finer guards, which are the ones a target can hit by reporting a field it
    does not actually have.
    """

    target = _clean_target()
    cursor: object = target
    for key in path[:-1]:
        cursor = cursor[key]
    cursor[path[-1]] = value
    result = SCENARIO.follow_up_check(target)
    assert not result["passed"], f"{path} = {value!r} scored clean"
    assert expected in result["findings"]


def test_a_call_answered_by_the_stale_endpoint_fails_however_it_self_reports() -> None:
    """The headline property, graded from evidence rather than from a flag.

    ``stale_endpoint_rejected`` is the target's own boolean. A run that was in
    fact served by the stale endpoint can set it to ``True``; only comparing
    the reported ``answered_endpoint`` against the gold's endpoint identities
    catches that.
    """

    target = _clean_target()
    target["workflow_switch"]["answered_endpoint"] = GOLD["stale_endpoint"]
    target["workflow_switch"]["stale_endpoint_rejected"] = True
    result = SCENARIO.follow_up_check(target)
    assert not result["passed"]
    assert "post_switch_call_served_by_stale_endpoint" in result["findings"]


def test_a_call_answered_by_an_endpoint_the_gold_does_not_declare_is_caught() -> None:
    target = _clean_target()
    target["workflow_switch"]["answered_endpoint"] = "endpoint-v3"
    result = SCENARIO.follow_up_check(target)
    assert not result["passed"]
    assert "post_switch_call_served_by_unknown_endpoint:endpoint-v3" in result["findings"]


@pytest.mark.parametrize("field", ["stale_endpoint", "new_endpoint"])
def test_a_gold_missing_an_endpoint_identity_is_ungraded(
    tmp_path: Path, field: str
) -> None:
    oracle = {key: value for key, value in GOLD.items() if key != field}
    result = _scenario_with_oracle(tmp_path, oracle).follow_up_check(_clean_target())
    assert result["status"] == "ungraded"
    assert not result["passed"]
    assert "oracle_gold_malformed" in result["findings"]


def test_missing_sub_evidence_is_not_examined_not_conflated_with_a_clean_pass() -> None:
    for key in ("diagnosis", "phase_evidence", "workflow_switch"):
        target = _clean_target()
        del target[key]
        result = SCENARIO.follow_up_check(target)
        assert not result["passed"], f"missing {key} scored clean"
        assert any(finding.endswith("_not_examined") for finding in result["findings"]), (
            f"missing {key} produced findings {result['findings']!r} without a not_examined code"
        )


def test_each_headline_mutation_produces_its_own_distinct_finding_code() -> None:
    """Pin the *code* each headline mutation emits, not merely that it fails.

    This is deliberately not a positive control: it does not neuter any
    branch. Its value is that a refactor which collapses two properties onto
    one finding code, or renames a code, breaks here rather than passing with
    a differently-shaped failure. Branch-level coverage -- that each guard is
    individually load-bearing -- comes from the per-branch tests above and
    below, not from this test.
    """

    findings_seen: set[str] = set()
    for mutate in (
        lambda t: t["diagnosis"]["attempt_classifications"].__setitem__("1", "build_broken"),
        lambda t: (
            t["diagnosis"].__setitem__("build_status_claim", "unhealthy"),
            t["diagnosis"].__setitem__("build_status_evidence_ref", "serve-phase/attempt-1/bind"),
        ),
        lambda t: t["diagnosis"].__setitem__("retry_strategy", "retry_until_bound_free"),
        lambda t: t["attempts"]["1"].__setitem__("stderr", "boom"),
        lambda t: t["workflow_switch"].__setitem__("stale_endpoint_rejected", False),
        lambda t: t["phase_evidence"].__setitem__("switch_turn", 1),
    ):
        target = _clean_target()
        mutate(target)
        result = SCENARIO.follow_up_check(target)
        assert not result["passed"]
        findings_seen.update(result["findings"])
    assert {
        "attempt_misclassified:build_broken",
        "unhealthy_claim_not_backed_by_build_phase_evidence",
        "retry_until_lucky_detected:retry_until_bound_free",
        "attempt_leaked_stderr:1",
        "stale_endpoint_not_confirmed_rejected",
        "switch_call_before_restart",
    } <= findings_seen


# --------------------------------------------------------------------------
# Real substrate: the broker fault and the workflow switch are actually
# driven, not narrated. The subprocess shim below is the same one
# test_supervisor_knobs.py uses to prove the occupied-port fault produces no
# stderr and repeats identically by attempt number.
# --------------------------------------------------------------------------


def _available_port() -> int:
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = int(sock.getsockname()[1])
    sock.close()
    return port


def _run_broker_shim(plan: BrokerFaultPlan, attempt: int, real_child: Path) -> tuple[int, bytes]:
    # ``real_child`` reaches the subprocess through the plan's environment
    # (NXD_EVAL_BROKER_REAL_ENTRYPOINT), not through this signature; it stays
    # a parameter so callers cannot silently drive a plan built for a
    # different child.
    assert Path(plan.real_entrypoint) == real_child
    environment = dict(plan.environment_for_attempt(attempt))
    completed = subprocess.run(
        [sys.executable, str(broker_entrypoint_path()), "--port", str(_available_port())],
        env={**environment, "PYTHONIOENCODING": "utf-8"},
        capture_output=True,
        check=False,
        timeout=5,
    )
    return completed.returncode, completed.stderr


def test_real_broker_attempts_reconcile_against_the_gold_and_pass_grading(tmp_path: Path) -> None:
    real_child = tmp_path / "real-child.py"
    real_child.write_text(
        "import socket, sys\n"
        "port = int(sys.argv[sys.argv.index('--port') + 1])\n"
        "sock = socket.socket()\n"
        "try:\n"
        "    sock.bind(('127.0.0.1', port))\n"
        "except OSError:\n"
        "    raise SystemExit(41)\n"
        "else:\n"
        "    raise SystemExit(0)\n",
        encoding="utf-8",
    )
    plan = BrokerFaultPlan(
        {GOLD["fault_attempt"]: BrokerFaultShape(GOLD["fault_shape"])},
        real_entrypoint=real_child,
    )
    faulted_code, faulted_stderr = _run_broker_shim(plan, GOLD["fault_attempt"], real_child)
    cleared_code, cleared_stderr = _run_broker_shim(plan, GOLD["cleared_attempt"], real_child)

    # On both attempts the shim execs the real child. On the faulted attempt
    # the shim is already holding the port, so it is the *real child's* bind
    # that fails -- and it fails silently, because the shim redirected fd 2 to
    # /dev/null before the exec and the child inherits it. That silence is a
    # harness property. On the cleared attempt the child binds and exits zero;
    # its empty stderr is a property of this test's own stub child, not of the
    # shim.
    assert faulted_code == 41, "the faulted attempt's exit code is the real child's failed bind"
    assert faulted_stderr == b""
    assert cleared_code == 0
    assert cleared_stderr == b""

    target = _clean_target()
    target["attempts"] = {
        str(GOLD["fault_attempt"]): {
            "fault": GOLD["fault_shape"],
            "outcome": "bind_failed",
            "stderr": faulted_stderr.decode("utf-8"),
            "evidence_ref": f"serve-phase/attempt-{GOLD['fault_attempt']}/bind",
        },
        str(GOLD["cleared_attempt"]): {
            "fault": "none",
            "outcome": "served",
            "stderr": cleared_stderr.decode("utf-8"),
            "evidence_ref": f"serve-phase/attempt-{GOLD['cleared_attempt']}/bind",
        },
    }
    result = SCENARIO.follow_up_check(target)
    assert result == {"status": "examined", "passed": True, "findings": []}

    # Attempt-keyed and repeats identically: running the same attempt numbers
    # again produces the same shape, so the schedule is not raced.
    repeat_faulted_code, repeat_faulted_stderr = _run_broker_shim(plan, GOLD["fault_attempt"], real_child)
    assert repeat_faulted_code == faulted_code
    assert repeat_faulted_stderr == faulted_stderr == b""


class _MockServerTransport:
    """Adapt the harness's own async server handle to the restart protocol."""

    def __init__(self, workflow: str, config: object) -> None:
        self.workflow = workflow
        self._handle = MockSourceHandle(config)

    def start(self) -> "_MockServerTransport":
        self._handle.start()
        return self

    def cleanup(self) -> None:
        self._handle.stop()

    @property
    def data_url(self) -> str:
        return self._handle.server.data_url


def _workflow_route_config(workflow: str, endpoint: str) -> object:
    return load_config(
        {
            "version": 1,
            "routes": [
                {
                    "path": "/workflow",
                    "method": "GET",
                    "response": {"json": {"workflow": workflow, "endpoint": endpoint}},
                }
            ],
        }
    )


_OLD_CONFIG = _workflow_route_config("orders-workflow-v1", "endpoint-v1")
_NEW_CONFIG = _workflow_route_config("orders-workflow-v2", "endpoint-v2")


def _first_call(transport: _MockServerTransport, workflow: str) -> EndpointObservation:
    with urllib.request.urlopen(transport.data_url + "/workflow", timeout=5) as response:
        body = json.loads(response.read().decode("utf-8"))
    return EndpointObservation(workflow, body["workflow"], body["endpoint"])


def _restart(workflow: str) -> _MockServerTransport:
    config = _NEW_CONFIG if workflow == "orders-workflow-v2" else _OLD_CONFIG
    return _MockServerTransport(workflow, config).start()


def test_real_workflow_switch_call_lands_on_the_new_endpoint_and_passes_grading() -> None:
    old = _MockServerTransport("orders-workflow-v1", _OLD_CONFIG).start()
    plan = WorkflowSwitchPlan(GOLD["from_workflow"], GOLD["to_workflow"])
    try:
        replacement, evidence = script_restart_and_switch(
            old,
            plan,
            restart=_restart,
            first_call=_first_call,
            stale_endpoint="endpoint-v1",
        )
        try:
            assert evidence.answered_workflow == GOLD["to_workflow"]
            assert evidence.answered_endpoint == "endpoint-v2"
            assert evidence.stale_endpoint_rejected is True

            target = _clean_target()
            target["workflow_switch"] = evidence.to_dict()
            result = SCENARIO.follow_up_check(target)
            assert result == {"status": "examined", "passed": True, "findings": []}
        finally:
            replacement.cleanup()
    except BaseException:
        old.cleanup()
        raise

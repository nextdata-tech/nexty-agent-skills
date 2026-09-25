"""Declarative scenario packages and their fail-closed loader.

The invariant enforced here is that a runnable scenario contains every piece
of its fixture identity, operator script, planted difficulty, gate wiring, and
gold reference.  Keeping those values in package data makes a third scenario
addable without changing Python and prevents an omitted plant or answer file
from becoming an unmeasured pass.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType

import yaml

from . import followups
from .followups import FollowUpContext, FollowUpError
from .support import (
    _MISSING,
    _manifest_row_counts,
    _mapping,
    _read_document,
    _string,
    _unknown,
    ScenarioError,
)
from .grading import (
    GATE_PHASES,
    Finding,
    GoldRowSet,
    GateResult,
    gate_follow_up,
    gate_query,
    gold_rowset,
)
from .grading.statistics import RepeatabilityTier, repeatability_plan
from .mockrest.config import ConfigError as MockRestConfigError
from .mockrest.config import fixture_source_tables
from .mockrest.config import ScenarioConfig as MockRouteTable
from .mockrest.config import load_config as load_route_table
from .operator import EventSchedule, OperatorScript, PersonaCard, load_event_cards, load_persona
from .operator.answer_sheet import AnswerSheet, load_answer_sheet
from .synthgen import GenerationResult, generate_dataset, get_dataset


class GoldArtifactError(ScenarioError):
    """A committed or generated gold reference could not be graded."""


def _strings(value: object, location: str, *, allow_empty: bool = False) -> tuple[str, ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise ScenarioError(f"{location} must be a list of strings")
    result: list[str] = []
    for index, item in enumerate(value):
        result.append(_string(item, f"{location}[{index}]") )
    if not result and not allow_empty:
        raise ScenarioError(f"{location} must not be empty")
    return tuple(result)


def _positive_int(value: object, location: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ScenarioError(f"{location} must be a positive integer")
    return value


def _relative_reference(root: Path, value: object, location: str, *, must_exist: bool = True) -> Path:
    reference = _string(value, location)
    path = Path(reference)
    if path.is_absolute():
        raise ScenarioError(f"{location} must be relative to the scenario package")
    resolved = (root / path).resolve()
    if must_exist and not resolved.is_file():
        raise ScenarioError(f"{location} does not resolve to a file: {reference}")
    return resolved


def _agent_artifact_reference(value: object, location: str) -> str | None:
    """Validate an agent-written artifact path without resolving it on disk."""

    if value is None:
        return None
    reference = _string(value, location)
    path = Path(reference)
    if path.is_absolute() or not path.parts or any(part in {"", ".", ".."} for part in path.parts):
        raise ScenarioError(f"{location} must be a contained relative path")
    if path.suffix.casefold() != ".json":
        raise ScenarioError(f"{location} must name a JSON artifact")
    if "artifacts" in path.parts:
        raise ScenarioError(f"{location} may not target the runner evidence directory")
    return path.as_posix()


@dataclass(frozen=True, slots=True)
class FixtureSpec:
    """The named, seeded fixture generated at scenario-run start."""

    dataset: str
    seed: int
    variant: str
    plant: str = ""

    def generate(self, out_dir: str | Path) -> GenerationResult:
        """Generate this fixture into a disposable run directory."""

        return generate_dataset(self.dataset, self.seed, out_dir)


@dataclass(frozen=True, slots=True)
class RepeatabilitySpec:
    """Scenario-declared epochs and the rule used to certify them.

    The fields are declarative metadata for the repeatability runner.  This
    loader validates their tier, epoch, gate, and confidence shape; the
    downstream statistics unit owns the actual certificate calculation.
    """

    tier: RepeatabilityTier
    epochs: int
    certification_rule: str
    gates: tuple[str, ...]
    lower_bound: float | None
    confidence: float | None

    @property
    def epoch_count(self) -> int:
        """Return the declared number of repeatability epochs."""

        return self.epochs


@dataclass(frozen=True, slots=True)
class GateSpec:
    """A named gate binding; scenario-specific behaviour is declarative."""

    name: str
    kind: str
    settings: Mapping[str, object]

    def to_mapping(self) -> dict[str, object]:
        """Return the stable gate declaration."""

        return {"kind": self.kind, **dict(self.settings)}


@dataclass(frozen=True, slots=True)
class QueryAssessment:
    """EX-scored query result plus a known-naive diagnosis."""

    verdict: str
    gold_gate: GateResult
    naive_gate: GateResult
    actual_rows: tuple[dict[str, object], ...]


class AgentEvidence(dict):
    """An agent-authored evidence artifact, tagged so the shim skips it.

    ``follow_up_check`` accepts a mapping carrying ``closure``/``query_rows``/
    ``fixture_dir``/``row_count_oracle``/``row_counts`` as the legacy
    positional calling convention and unwraps it.  A declared evidence
    artifact is not that -- it is the agent's own JSON object, and an agent
    that happens to add a ``closure`` field for context would have had its
    target silently replaced by ``None`` and zeroed the whole follow-up gate.
    Refusing those key names would only move the trap; the artifact simply
    must not be routed through the shim at all.
    """


@dataclass(frozen=True, slots=True)
class Scenario:
    """One fully resolved, data-backed evaluation scenario."""

    package_dir: Path
    scenario_id: str
    tier: str
    run_order: int
    fixture: FixtureSpec
    coverage: Mapping[str, str]
    turn_budget: int
    repeatability: RepeatabilitySpec
    persona_path: Path
    persona: PersonaCard
    answer_sheet_path: Path
    answer_sheet: AnswerSheet
    events_path: Path
    events: EventSchedule
    phase_map: Mapping[int, int]
    required_plants: frozenset[str]
    gates: Mapping[str, GateSpec]
    gold: Mapping[str, Path]
    gold_refs: Mapping[str, str]
    operator_script: OperatorScript
    # An optional mockrest route table validated at load time.  A declaring
    # scenario is the one ``environment._scenario_route_config`` finds (it
    # looks for this exact attribute name), which is what lets the runner
    # start a real mock source and compute route_fidelity instead of leaving
    # it "not-applicable". ``None`` means this scenario names no source, the
    # same as every scenario before this field existed.
    route_table: MockRouteTable | None = None
    # Optional JSON evidence authored during a run and consumed by the
    # scenario-specific follow-up. It is always relative to the runner's
    # artifact root; hidden gold is never inferred from this path.
    follow_up_artifact: str | None = None

    @property
    def id(self) -> str:
        """Return the scenario identity."""

        return self.scenario_id

    @property
    def dataset(self) -> str:
        """Return the fixture dataset name."""

        return self.fixture.dataset

    @property
    def seed(self) -> int:
        """Return the pinned fixture seed."""

        return self.fixture.seed

    @property
    def fixture_variant(self) -> str:
        """Return the exact fixture variant exercised by this scenario."""

        return self.fixture.variant

    @property
    def plant_vocabulary(self) -> frozenset[str]:
        """Return the closed planted-difficulty vocabulary for this dataset."""

        return _plant_vocabulary(self.fixture.dataset, self.fixture.plant)

    @property
    def repeatability_tier(self) -> RepeatabilityTier:
        """Return the typed repeatability tier."""

        return self.repeatability.tier

    @property
    def epochs(self) -> int:
        """Return the tier-determined epoch count."""

        return self.repeatability.epochs

    @property
    def script(self) -> OperatorScript:
        """Return the fully resolved operator script."""

        return self.operator_script

    @property
    def operator_script_hash(self) -> str:
        """Return the manifest hash, including the complete persona card."""

        return scenario_script_hash(self.operator_script)

    @property
    def script_hash(self) -> str:
        """Compatibility spelling for the manifest-facing script hash."""

        return self.operator_script_hash

    @property
    def gold_paths(self) -> Mapping[str, Path]:
        """Return resolved package gold artifact paths."""

        return self.gold

    @property
    def has_scoreable_answer_gold(self) -> bool:
        """Whether this scenario declares the answer artifact needed by query grading."""

        return "answer" in self.gold

    @property
    def stages_capability_shortfall(self) -> bool:
        """Whether the declared source exposes a gradeable capability shortfall."""

        if self.route_table is None:
            return False
        capability = self.route_table.capability
        metrics = capability.get("metrics") if isinstance(capability, Mapping) else None
        metric_terms = capability.get("metric_terms") if isinstance(capability, Mapping) else None
        if not isinstance(metrics, Mapping) or not isinstance(metric_terms, Mapping):
            return False
        return any(
            label in {"impossible", "proxy"} and name in metric_terms
            for name, label in metrics.items()
        )

    @property
    def stages_definition_change(self) -> bool:
        """Whether the scenario declares a mid-run narrowing definition change."""

        setting = self.gates["narrowing"].settings.get("definition_change")
        return isinstance(setting, Mapping)

    def generate_fixture(self, out_dir: str | Path) -> GenerationResult:
        """Generate the pinned source and gold fixture for one run."""

        return self.fixture.generate(out_dir)

    def gold_path(self, name: str, fixture_dir: str | Path | None = None) -> Path:
        """Resolve a declared gold artifact in the package or run fixture."""

        try:
            relative = self.gold_refs[name]
        except KeyError as exc:
            raise ScenarioError(f"unknown gold artifact {name!r}") from exc
        if fixture_dir is None:
            return self.gold[name]
        path = (Path(fixture_dir) / relative).resolve()
        if not path.is_file():
            raise GoldArtifactError(f"generated gold artifact does not exist: {relative}")
        return path

    def load_gold(self, name: str = "answer", fixture_dir: str | Path | None = None) -> GoldRowSet:
        """Load a declared row-set through the deterministic EX scorer."""

        result = gold_rowset(self.gold_path(name, fixture_dir))
        if not result.passed or not isinstance(result.value, GoldRowSet):
            detail = result.findings[0].detail if result.findings else "gold row-set was not examined"
            raise GoldArtifactError(f"gold artifact {name!r} was rejected: {detail}")
        return result.value

    def raw_gold(self, name: str, fixture_dir: str | Path | None = None) -> object:
        """Read a declared JSON artifact after resolving its package path."""

        path = self.gold_path(name, fixture_dir)
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise GoldArtifactError(f"could not read gold artifact {name!r}: {exc}") from exc

    @property
    def control_total(self) -> float:
        """Return the independent control total from the declared gold."""

        if "control_total" not in self.gold:
            raise ScenarioError(f"scenario {self.scenario_id} declares no control total")
        raw = self.raw_gold("control_total")
        if not isinstance(raw, list) or len(raw) != 1 or not isinstance(raw[0], Mapping):
            raise ScenarioError("control total gold must contain one object row")
        value = raw[0].get("control_total")
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ScenarioError("control total gold must contain a numeric control_total")
        return float(value)

    def graded_control_total(self) -> float:
        """Sum the exact graded per-region values in the answer row-set."""

        rows = self.load_gold("answer").rows
        try:
            return sum(float(row["regional_revenue"]) for row in rows)
        except (KeyError, TypeError, ValueError) as exc:
            raise ScenarioError("answer gold has no numeric regional_revenue values") from exc

    def reconcile_control_total(self, answer: object, fixture_dir: str | Path | None = None) -> object:
        """Reconcile an answer against the independent control-total artifact."""

        from .grading import control_total_oracle

        observed = answer
        if isinstance(answer, Sequence) and not isinstance(answer, (str, bytes, bytearray)):
            values = [
                row.get("regional_revenue")
                for row in answer
                if isinstance(row, Mapping)
            ]
            if values and all(isinstance(value, (int, float)) and not isinstance(value, bool) for value in values):
                observed = {"control_total": round(sum(float(value) for value in values), 2)}
        return control_total_oracle(observed, self.raw_gold("control_total", fixture_dir))

    def score_query(
        self,
        rows: Sequence[Mapping[str, object]],
        fixture_dir: str | Path | None = None,
    ) -> QueryAssessment:
        """EX-score rows and classify a wrong result as naive or otherwise wrong."""

        actual = tuple(dict(row) for row in rows)
        gold = self.load_gold("answer", fixture_dir)
        gold_gate = gate_query(list(actual), gold)
        naive_gate = GateResult("query", False, 0, ())
        verdict = "correct" if gold_gate.passed else "other_wrong"
        if not gold_gate.passed and "diagnostics" in self.gold:
            diagnostics = self.raw_gold("diagnostics", fixture_dir)
            naive_rows = _naive_rows(diagnostics)
            if naive_rows is not None:
                naive_gate = gate_query(list(actual), naive_rows)
                if naive_gate.passed:
                    verdict = "expected_naive_fanout"
        return QueryAssessment(verdict, gold_gate, naive_gate, actual)

    def follow_up_check(
        self,
        closure: object,
        fixture_dir: str | Path | Sequence[Mapping[str, object]] | None = None,
        query_rows: Sequence[Mapping[str, object]] | None = None,
        *,
        row_count_oracle: object = _MISSING,
        source_evidence: object = _MISSING,
        operator_observations: object = _MISSING,
    ) -> Mapping[str, object]:
        """Run follow-up against a closure, with gold resolved separately.

        ``fixture_dir`` is the package fixture by default and may explicitly
        point at a generated fixture containing its gold.  It is never
        inferred from the closure target.  The sequence compatibility branch
        preserves the older ``follow_up_check(closure, query_rows)`` spelling.
        """

        if query_rows is None and _is_row_sequence(fixture_dir):
            query_rows = fixture_dir
            fixture_dir = None

        binding = self.gates["follow-up"]
        target = closure
        if isinstance(closure, Mapping) and not isinstance(closure, AgentEvidence) and (
            "closure" in closure
            or "query_rows" in closure
            or "fixture_dir" in closure
            or "row_count_oracle" in closure
            or "row_counts" in closure
        ):
            target = closure.get("closure")
            if query_rows is None:
                candidate = closure.get("query_rows")
                if isinstance(candidate, Sequence) and not isinstance(candidate, (str, bytes, bytearray)):
                    query_rows = [row for row in candidate if isinstance(row, Mapping)]
            if fixture_dir is None:
                candidate_fixture = closure.get("fixture_dir")
                if isinstance(candidate_fixture, (str, Path)):
                    fixture_dir = candidate_fixture
            if row_count_oracle is _MISSING:
                if "row_count_oracle" in closure:
                    row_count_oracle = closure["row_count_oracle"]
                elif "row_counts" in closure:
                    row_count_oracle = closure["row_counts"]
        context = FollowUpContext(
            fixture_dir=fixture_dir if isinstance(fixture_dir, (str, Path)) else None,
            row_count_oracle=row_count_oracle,
            source_evidence=source_evidence,
            operator_observations=operator_observations,
        )
        try:
            kind = followups.get(binding.kind)
        except FollowUpError:
            # A kind the loader accepted but no module registers can only mean
            # a package registered under one name and graded under another.
            result: dict[str, object] = {
                "status": "not-examined",
                "passed": False,
                "findings": ["unknown_follow_up_kind"],
            }
        else:
            try:
                result = dict(kind.handler(self, target, binding.settings, context))
                if query_rows is not None and self.has_scoreable_answer_gold:
                    assessment = self.score_query(
                        query_rows,
                        fixture_dir if isinstance(fixture_dir, (str, Path)) else None,
                    )
                    result["query_verdict"] = assessment.verdict
                    result["query_gate_passed"] = assessment.gold_gate.passed
                    if "control_total" in self.gold:
                        control = self.reconcile_control_total(
                            query_rows,
                            fixture_dir if isinstance(fixture_dir, (str, Path)) else None,
                        )
                        result["control_total_verdict"] = control.outcome
                        if not control.passed:
                            result.setdefault("findings", [])
                            result["findings"] = [*result["findings"], *control.codes]
            except GoldArtifactError as exc:
                # A committed reference is harness-owned. If it cannot be read
                # or validated, the follow-up did not measure the agent; void
                # it explicitly instead of turning the agent's result into a
                # failure.
                return {
                    "status": "ungraded",
                    "passed": False,
                    "findings": ["gold_artifact_unreadable"],
                    "detail": str(exc),
                }
        return result

    def follow_up_gate(
        self,
        closure: object,
        fixture_dir: str | Path | Sequence[Mapping[str, object]] | None = None,
        query_rows: Sequence[Mapping[str, object]] | None = None,
        *,
        fired_plants: object = _MISSING,
        row_count_oracle: object = _MISSING,
        source_evidence: object = _MISSING,
        operator_observations: object = _MISSING,
    ) -> GateResult:
        """Adapt the declared follow-up check to the settled follow-up gate type."""

        plant_input = fired_plants
        if (
            fired_plants is not _MISSING
            and isinstance(self.gates["follow-up"].settings.get("plant_evidence"), Mapping)
            and self.gates["follow-up"].settings.get("plant_evidence")
            and isinstance(fixture_dir, (str, Path))
            and not isinstance(fired_plants, Mapping)
        ):
            manifest = _read_document(fixture_dir, "fixture-manifest.json")
            if manifest is not _MISSING:
                plant_input = {"fired_plant_ids": fired_plants, "fixture_manifest": manifest}
        prerequisite = self.check_fired_plants(plant_input)
        if not prerequisite.passed:
            return GateResult(
                "follow-up",
                False,
                0,
                prerequisite.findings,
                examined=prerequisite.examined,
                ungraded=prerequisite.ungraded,
            )
        result = self.follow_up_check(
            closure,
            fixture_dir,
            query_rows,
            row_count_oracle=row_count_oracle,
            source_evidence=source_evidence,
            operator_observations=operator_observations,
        )
        base = gate_follow_up(result)
        raw_findings = result.get("findings", ())
        findings = tuple(
            Finding(str(code), f"scenario follow-up check: {code}")
            for code in raw_findings
            if isinstance(code, str)
        )
        if not findings:
            return base
        return GateResult(
            "follow-up",
            False,
            0,
            findings,
            examined=base.examined,
            # Only an explicit ``ungraded`` voids the run. ``not-examined``
            # used to void it too, which meant an agent that produced no
            # evidence artifact at all got its run discarded instead of failed
            # -- the "dodge a gate by producing nothing" hole the requiredness
            # work exists to close, surviving in the follow-up path. A live run
            # stalled, built nothing, and scored ``ungraded`` rather than a
            # loss. ``gates.py`` already states the policy this restores:
            # ungraded is for a planted check that fired and measured nothing.
            ungraded=base.ungraded or result.get("status") == "ungraded",
        )

    def check_follow_up(
        self,
        closure: object,
        fixture_dir: str | Path | Sequence[Mapping[str, object]] | None = None,
        query_rows: Sequence[Mapping[str, object]] | None = None,
        *,
        fired_plants: object = _MISSING,
        row_count_oracle: object = _MISSING,
        source_evidence: object = _MISSING,
        operator_observations: object = _MISSING,
    ) -> GateResult:
        """Alias for callers that use the gate-oriented spelling."""

        return self.follow_up_gate(
            closure,
            fixture_dir,
            query_rows,
            fired_plants=fired_plants,
            row_count_oracle=row_count_oracle,
            source_evidence=source_evidence,
            operator_observations=operator_observations,
        )

    def check_fired_plants(self, run_or_ids: object) -> GateResult:
        """Check the runner-owned plant evidence before build or follow-up grading.

        The runner must call this prerequisite with the completed run (or its
        ``fired_plant_ids``) before it grades build and follow-up criteria.
        Missing plant evidence is ungraded; observed but missing plants are
        also ungraded because the declared difficulty never fired.
        """

        candidate: object = run_or_ids
        manifest: object = _MISSING
        if hasattr(run_or_ids, "fired_plant_ids"):
            candidate = getattr(run_or_ids, "fired_plant_ids")
        elif isinstance(run_or_ids, Mapping):
            candidate = run_or_ids.get("fired_plant_ids", run_or_ids.get("fired_plants", _MISSING))
            manifest = run_or_ids.get("fixture_manifest", run_or_ids.get("manifest", _MISSING))
        plant_evidence = self.gates["follow-up"].settings.get("plant_evidence", {})
        manifest_evidence_available = isinstance(plant_evidence, Mapping) and bool(plant_evidence) and manifest is not _MISSING
        if candidate is _MISSING and manifest_evidence_available:
            candidate = ()
        if candidate is _MISSING or isinstance(candidate, (str, bytes, bytearray)):
            return GateResult(
                "follow-up",
                False,
                0,
                (Finding("plants_not_examined", "runner supplied no fired-plant evidence"),),
                examined=False,
                ungraded=True,
            )
        if not isinstance(candidate, Iterable):
            return GateResult(
                "follow-up",
                False,
                0,
                (Finding("plants_not_examined", "fired-plant evidence is not iterable"),),
                examined=False,
                ungraded=True,
            )
        fired = {item for item in candidate if isinstance(item, str)}
        if isinstance(plant_evidence, Mapping) and plant_evidence:
            if manifest is _MISSING:
                return GateResult(
                    "follow-up",
                    False,
                    0,
                    (Finding("plants_not_examined", "fixture-manifest plant evidence is absent"),),
                    examined=False,
                    ungraded=True,
                )
            observed_counts = _manifest_row_counts(manifest)
            if observed_counts is None:
                return GateResult(
                    "follow-up",
                    False,
                    0,
                    (Finding("plants_not_examined", "fixture-manifest row counts are absent or unreadable"),),
                    examined=False,
                    ungraded=True,
                )
            for plant in sorted(self.required_plants):
                evidence = plant_evidence.get(plant)
                if not isinstance(evidence, Mapping):
                    return GateResult(
                        "follow-up",
                        False,
                        0,
                        (Finding("plants_not_examined", f"plant evidence is not declared for {plant}"),),
                        examined=False,
                        ungraded=True,
                    )
                resource = evidence.get("resource")
                expected_count = evidence.get("row_count")
                if not isinstance(resource, str) or isinstance(expected_count, bool) or not isinstance(expected_count, int):
                    return GateResult(
                        "follow-up",
                        False,
                        0,
                        (Finding("plants_not_examined", f"plant evidence is malformed for {plant}"),),
                        examined=False,
                        ungraded=True,
                    )
                if observed_counts.get(resource, _MISSING) != expected_count:
                    return GateResult(
                        "follow-up",
                        False,
                        0,
                        (Finding("required_plant_not_fired", "declared planted difficulty was not observed in the fixture manifest", plant),),
                        examined=True,
                        ungraded=True,
                    )
            return GateResult("follow-up", True, 0, (), examined=True, ungraded=False)
        missing = self.required_plants - fired
        if missing:
            return GateResult(
                "follow-up",
                False,
                0,
                (Finding("required_plant_not_fired", "declared planted difficulty did not fire", sorted(missing)),),
                examined=True,
                ungraded=True,
            )
        return GateResult("follow-up", True, 0, (), examined=True, ungraded=False)

    fired_plants_check = check_fired_plants


ScenarioDeclaration = Scenario


_SCENARIO_KEYS = {
    "version",
    "id",
    "tier",
    "run_order",
    "fixture",
    "coverage",
    "turn_budget",
    "repeatability",
    "persona",
    "answer_sheet",
    "events",
    "phase_map",
    "required_plants",
    "gates",
    "gold",
    "operator",
}
# Genuinely optional top-level keys: absent by default across every existing
# package, so they live outside ``_SCENARIO_KEYS`` rather than being added to
# it, which would make every existing scenario.yaml fail the "missing key(s)"
# check the moment this key exists at all.
_OPTIONAL_SCENARIO_KEYS = {"route_table", "follow_up_artifact"}
_FIXTURE_KEYS = {"dataset", "seed", "variant", "plant"}
_REPEATABILITY_KEYS = {"tier", "epochs", "certification"}
_CERTIFICATION_KEYS = {"rule", "gates", "lower_bound", "confidence"}
_OPERATOR_KEYS = {"sentinel", "obstacle_terms"}
_COVERAGE_KEYS = {"variant", "untested"}
_DEFINITION_CHANGE_KEYS = {"trigger_turn", "changed_metrics"}
_SCENARIO_TIERS = frozenset({"smoke", "T0", "core", "full", "live"})
# The tiers whose scenarios cannot be graded from a recording. A live-tier
# scenario's pass criteria are what an agent *did* across turns, so replaying
# a stored session grades the recording rather than the agent. Naming the set
# here rather than testing ``tier == "live"`` at each call site keeps the two
# CLIs from drifting apart on what "live" means.
_LIVE_ONLY_TIERS = frozenset({"live"})
# The legacy spelling maps onto the tier it is an alias for, so selection
# treats the two as one tier rather than as two that never intersect.
_TIER_ALIASES = {"T0": "smoke"}
# Public alias: the CLIs offer these as argparse choices, so a bad --tier is
# a usage error rather than a traceback out of select_tier.
SCENARIO_TIERS = _SCENARIO_TIERS


def requires_live_session(tier: str) -> bool:
    """Return whether a tier can only be run against a live agent session.

    ``smoke``, ``core``, and ``full`` scenarios grade supplied evidence and
    can be replayed without an authenticated session. ``live`` cannot: its
    scenarios grade multi-turn agent behaviour, which a recording cannot
    produce. Callers use this to refuse a replay-mode run rather than to
    produce a clean-looking report over evidence no agent generated.
    """

    return _TIER_ALIASES.get(tier, tier) in _LIVE_ONLY_TIERS


def _canonical_hash(value: object) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _is_row_sequence(value: object) -> bool:
    return isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)) and all(
        isinstance(row, Mapping) for row in value
    )


def _declared_markers(value: object, *, named: bool) -> Iterable[bytes]:
    """Yield every string reached under a key that names a sentinel."""

    if isinstance(value, str):
        if named and value:
            yield value.encode("utf-8")
    elif isinstance(value, Mapping):
        for key, item in value.items():
            yield from _declared_markers(
                item,
                named=named or "sentinel" in str(key).casefold(),
            )
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        for item in value:
            yield from _declared_markers(item, named=named)


def declared_sentinels(scenario: object) -> frozenset[bytes]:
    """Return every marker a scenario's gates declare, as raw bytes.

    Redaction before an external model provider is unconditional, and the
    generated fixture manifest is not a complete inventory of what a scenario
    planted: ``capability-shortfall`` declares its graded ``pii_sentinel``
    under ``gates.follow-up`` and plants it in the mock-source route table,
    which ``marker_values`` never reads.  Any gate setting whose key names a
    sentinel is one, wherever the scenario chose to plant it.  A scenario-like
    object that declares no gates declares no sentinels.
    """

    gates = getattr(scenario, "gates", None)
    if not isinstance(gates, Mapping):
        return frozenset()
    return frozenset(
        marker
        for gate in gates.values()
        for marker in _declared_markers(getattr(gate, "settings", {}), named=False)
    )


def scenario_script_hash(script: object) -> str:
    """Hash a resolved script while retaining every persona field."""

    if not hasattr(script, "to_mapping") or not hasattr(script, "persona"):
        raise TypeError("script must expose to_mapping and persona")
    material = dict(script.to_mapping())
    material["persona"] = script.persona.to_mapping()
    return _canonical_hash(material)


def _plant_vocabulary(dataset: str, explicit_plant: str | None = None) -> frozenset[str]:
    """Derive plant identifiers from dataset injectors and its explicit plant."""

    definition = get_dataset(dataset)
    result = {injector.name for injector in definition.injectors}
    declared_plant = getattr(definition, "plant", None)
    if not isinstance(declared_plant, str) or not declared_plant:
        raise ScenarioError(f"dataset {dataset!r} has no explicit planted-difficulty declaration")
    if explicit_plant is not None and explicit_plant != declared_plant:
        raise ScenarioError(
            f"fixture.plant must be {declared_plant!r} for dataset {dataset!r}"
        )
    result.add(declared_plant)
    return frozenset(result)


def _validate_plants(
    dataset: str,
    explicit_plant: str,
    required: frozenset[str],
    events: EventSchedule,
) -> None:
    allowed = _plant_vocabulary(dataset, explicit_plant)
    unknown = sorted(required - allowed)
    if unknown:
        raise ScenarioError("required_plants contains unknown identifier(s): " + ", ".join(unknown))
    planted = events.planted_card_ids()
    unknown_events = sorted(planted - allowed)
    if unknown_events:
        raise ScenarioError("events declare unknown planted identifier(s): " + ", ".join(unknown_events))
    missing_events = sorted(required - planted)
    if missing_events:
        raise ScenarioError("required_plants must be backed by planted event(s): " + ", ".join(missing_events))


def _parse_coverage(value: object, fixture_variant: str) -> Mapping[str, str]:
    raw = _mapping(value, "coverage")
    _unknown(raw, _COVERAGE_KEYS, "coverage")
    if set(raw) != _COVERAGE_KEYS:
        raise ScenarioError("coverage requires variant and untested")
    variant = _string(raw["variant"], "coverage.variant")
    if variant != fixture_variant:
        raise ScenarioError("coverage.variant must match fixture.variant")
    untested = _string(raw["untested"], "coverage.untested")
    return MappingProxyType({"variant": variant, "untested": untested})


def _parse_repeatability(value: object) -> RepeatabilitySpec:
    raw = _mapping(value, "repeatability")
    _unknown(raw, _REPEATABILITY_KEYS, "repeatability")
    if set(raw) != _REPEATABILITY_KEYS:
        raise ScenarioError("repeatability requires tier, epochs, and certification")
    try:
        tier = RepeatabilityTier(_string(raw["tier"], "repeatability.tier"))
    except ValueError as exc:
        raise ScenarioError(f"unknown repeatability tier: {raw.get('tier')!r}") from exc
    epochs = _positive_int(raw["epochs"], "repeatability.epochs")
    expected_epochs = repeatability_plan(tier)
    if epochs != expected_epochs:
        raise ScenarioError(f"repeatability.epochs must be {expected_epochs} for {tier.value}")
    certification = _mapping(raw["certification"], "repeatability.certification")
    _unknown(certification, _CERTIFICATION_KEYS, "repeatability.certification")
    required_certification = {"rule", "gates"}
    if not required_certification.issubset(certification):
        raise ScenarioError("repeatability.certification requires rule and gates")
    gates = _strings(certification["gates"], "repeatability.certification.gates")
    if any(gate not in {"build", "query"} for gate in gates):
        raise ScenarioError("repeatability certification gates must be build or query")
    rule = _string(certification["rule"], "repeatability.certification.rule")
    lower = certification.get("lower_bound")
    confidence = certification.get("confidence")
    if tier is RepeatabilityTier.DETERMINISTIC and rule not in {"wilson_lower_bound", "observed_epochs"}:
        raise ScenarioError("deterministic scenarios require Wilson or observed_epochs certification")
    if tier is RepeatabilityTier.DEMONSTRATED_ONCE and rule != "demonstrated_once":
        raise ScenarioError("demonstrated-once scenarios require demonstrated_once certification")
    if rule == "wilson_lower_bound":
        if not isinstance(lower, (float, int)) or isinstance(lower, bool) or not 0 < float(lower) <= 1:
            raise ScenarioError("Wilson certification requires a lower_bound in (0, 1]")
        if not isinstance(confidence, (float, int)) or isinstance(confidence, bool) or not 0 < float(confidence) < 1:
            raise ScenarioError("Wilson certification requires confidence in (0, 1)")
        lower_value: float | None = float(lower)
        confidence_value: float | None = float(confidence)
        if tier is RepeatabilityTier.DETERMINISTIC and (
            lower_value != 0.90 or confidence_value != 0.95
        ):
            raise ScenarioError(
                "deterministic certification requires lower_bound 0.90 and confidence 0.95"
            )
    elif rule == "observed_epochs":
        if lower is not None or confidence is not None:
            raise ScenarioError("deterministic certification requires lower_bound 0.90 and confidence 0.95 or null")
        lower_value = None
        confidence_value = None
    elif rule == "demonstrated_once":
        if lower is not None or confidence is not None:
            raise ScenarioError("demonstrated-once certification cannot declare Wilson bounds")
        lower_value = None
        confidence_value = None
    else:
        raise ScenarioError(f"unknown repeatability certification rule: {rule!r}")
    return RepeatabilitySpec(tier, epochs, rule, gates, lower_value, confidence_value)


def _parse_gates(value: object) -> Mapping[str, GateSpec]:
    raw = _mapping(value, "gates")
    expected = set(GATE_PHASES)
    if set(raw) != expected:
        missing = sorted(expected - set(raw))
        extra = sorted(set(raw) - expected)
        detail = [f"missing: {', '.join(missing)}"] if missing else []
        if extra:
            detail.append(f"unknown: {', '.join(extra)}")
        raise ScenarioError("gates must declare every phase gate (" + "; ".join(detail) + ")")
    parsed: dict[str, GateSpec] = {}
    for name in sorted(expected):
        entry = raw[name]
        if entry is None:
            # An omitted value means the gate runs its standard check.  Naming
            # the kind again would restate the gate's own name and could drift
            # away from it.
            parsed[name] = GateSpec(name, name, MappingProxyType({}))
            continue
        if isinstance(entry, str):
            kind = _string(entry, f"gates.{name}")
            settings: Mapping[str, object] = MappingProxyType({})
        else:
            mapping = _mapping(entry, f"gates.{name}")
            kind = _string(mapping.pop("kind", None), f"gates.{name}.kind")
            settings = MappingProxyType(mapping)
        parsed[name] = GateSpec(name, kind, settings)
    follow_up = parsed["follow-up"]
    if not followups.is_registered(follow_up.kind):
        raise ScenarioError(
            "gates.follow-up must declare a supported scenario-specific follow-up; "
            f"{follow_up.kind!r} is not registered (have: {sorted(followups.registered_names())})"
        )
    validate = followups.get(follow_up.kind).validate_settings
    if validate is not None:
        validate(follow_up.settings)
    return MappingProxyType(parsed)


def _validate_definition_change(gate: GateSpec, turn_count: int) -> None:
    """Validate the optional declaration that makes narrowing scoreable."""

    value = gate.settings.get("definition_change")
    if value is None:
        return
    raw = _mapping(value, "gates.narrowing.definition_change")
    _unknown(raw, _DEFINITION_CHANGE_KEYS, "gates.narrowing.definition_change")
    if set(raw) != _DEFINITION_CHANGE_KEYS:
        raise ScenarioError(
            "gates.narrowing.definition_change requires trigger_turn and changed_metrics"
        )
    trigger_turn = _positive_int(
        raw["trigger_turn"], "gates.narrowing.definition_change.trigger_turn"
    )
    if trigger_turn > turn_count:
        raise ScenarioError(
            "gates.narrowing.definition_change.trigger_turn must be within the operator turns"
        )
    _strings(
        raw["changed_metrics"],
        "gates.narrowing.definition_change.changed_metrics",
    )


def _parse_gold(
    root: Path,
    value: object,
    follow_up_kind: str,
) -> tuple[Mapping[str, Path], Mapping[str, str]]:
    raw = _mapping(value, "gold")
    expected = followups.get(follow_up_kind).gold_keys
    actual = set(raw)
    if actual != expected:
        missing = sorted(expected - actual)
        extra = sorted(actual - expected)
        detail: list[str] = []
        if missing:
            detail.append("missing: " + ", ".join(missing))
        if extra:
            detail.append("unknown: " + ", ".join(extra))
        raise ScenarioError("gold keys must match follow-up kind (" + "; ".join(detail) + ")")
    paths: dict[str, Path] = {}
    refs: dict[str, str] = {}
    for name, reference in raw.items():
        key = _string(name, "gold key")
        path = _relative_reference(root, reference, f"gold.{key}")
        paths[key] = path
        refs[key] = path.relative_to(root.resolve()).as_posix()
    return MappingProxyType(paths), MappingProxyType(refs)


def _parse_phase_map(value: object, turn_count: int) -> Mapping[int, int]:
    raw = _mapping(value, "phase_map")
    parsed: dict[int, int] = {}
    for key, phase in raw.items():
        try:
            turn = int(key)
        except (TypeError, ValueError) as exc:
            raise ScenarioError("phase_map keys must be positive turn integers") from exc
        parsed[turn] = _positive_int(phase, f"phase_map.{key}")
        if parsed[turn] > 7:
            raise ScenarioError("phase_map values must be protocol phases 1 through 7")
    expected = set(range(1, turn_count + 1))
    if set(parsed) != expected:
        raise ScenarioError("phase_map must declare exactly one phase for every operator turn")
    return MappingProxyType(dict(sorted(parsed.items())))


def _validate_certified_phase_reachability(
    repeatability: RepeatabilitySpec,
    phase_map: Mapping[int, int],
) -> None:
    reachable = set(phase_map.values())
    missing = sorted(gate for gate in repeatability.gates if GATE_PHASES[gate] not in reachable)
    if missing:
        raise ScenarioError(
            "repeatability certification gate phase(s) are unreachable: " + ", ".join(missing)
        )


def load_scenario(path: str | Path) -> Scenario:
    """Load one scenario directory or its ``scenario.yaml`` declaration."""

    source = Path(path)
    root = source if source.is_dir() else source.parent
    declaration_path = source / "scenario.yaml" if source.is_dir() else source
    try:
        raw_value = yaml.safe_load(declaration_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, yaml.YAMLError) as exc:
        raise ScenarioError(f"could not read scenario declaration {declaration_path}: {exc}") from exc
    raw = _mapping(raw_value, "scenario")
    _unknown(raw, _SCENARIO_KEYS | _OPTIONAL_SCENARIO_KEYS, "scenario")
    missing = sorted(_SCENARIO_KEYS - set(raw))
    if missing:
        raise ScenarioError(f"scenario is missing key(s): {', '.join(missing)}")
    version = raw["version"]
    if isinstance(version, bool) or not isinstance(version, int) or version != 1:
        raise ScenarioError("scenario.version must be integer 1")
    scenario_id = _string(raw["id"], "scenario.id")
    tier = _string(raw["tier"], "scenario.tier")
    run_order = raw["run_order"]
    if isinstance(run_order, bool) or not isinstance(run_order, int) or run_order < 1:
        raise ScenarioError("scenario.run_order must be a positive integer")
    if tier not in _SCENARIO_TIERS:
        raise ScenarioError(f"unknown scenario tier: {tier!r}")
    fixture_raw = _mapping(raw["fixture"], "fixture")
    _unknown(fixture_raw, _FIXTURE_KEYS, "fixture")
    if not {"dataset", "seed", "variant"}.issubset(fixture_raw):
        raise ScenarioError("fixture requires dataset, seed, and variant")
    dataset = _string(fixture_raw["dataset"], "fixture.dataset")
    get_dataset(dataset)
    seed = fixture_raw["seed"]
    if isinstance(seed, bool) or not isinstance(seed, int) or seed < 0:
        raise ScenarioError("fixture.seed must be a non-negative integer")
    explicit_plant = fixture_raw.get("plant")
    if explicit_plant is None:
        if getattr(get_dataset(dataset), "requires_explicit_plant", False):
            raise ScenarioError("fixture requires dataset, seed, variant, and plant")
        explicit_plant = getattr(get_dataset(dataset), "plant", None)
    fixture = FixtureSpec(
        dataset,
        seed,
        _string(fixture_raw["variant"], "fixture.variant"),
        _string(explicit_plant, "fixture.plant"),
    )
    coverage = _parse_coverage(raw["coverage"], fixture.variant)
    turn_budget = _positive_int(raw["turn_budget"], "turn_budget")
    repeatability = _parse_repeatability(raw["repeatability"])
    persona_path = _relative_reference(root, raw["persona"], "persona")
    answer_sheet_path = _relative_reference(root, raw["answer_sheet"], "answer_sheet")
    events_path = _relative_reference(root, raw["events"], "events")
    persona = load_persona(persona_path)
    answer_sheet = load_answer_sheet(answer_sheet_path)
    if answer_sheet.scenario_id != scenario_id:
        raise ScenarioError("answer_sheet.scenario_id must match scenario.id")
    if turn_budget < len(answer_sheet.turns):
        raise ScenarioError("turn_budget must be at least the number of operator turns")
    events = load_event_cards(events_path)
    phase_map = _parse_phase_map(raw["phase_map"], len(answer_sheet.turns))
    _validate_certified_phase_reachability(repeatability, phase_map)
    required_plants = frozenset(_strings(raw["required_plants"], "required_plants"))
    _validate_plants(dataset, fixture.plant, required_plants, events)
    operator_raw = _mapping(raw["operator"], "operator")
    _unknown(operator_raw, _OPERATOR_KEYS, "operator")
    if set(operator_raw) != _OPERATOR_KEYS:
        raise ScenarioError("operator requires sentinel and obstacle_terms")
    sentinel = operator_raw["sentinel"]
    if sentinel is not None and not isinstance(sentinel, str):
        raise ScenarioError("operator.sentinel must be text or null")
    obstacle_terms = _strings(operator_raw["obstacle_terms"], "operator.obstacle_terms", allow_empty=True)
    gates = _parse_gates(raw["gates"])
    _validate_definition_change(gates["narrowing"], len(answer_sheet.turns))
    _run_kind_hook(gates, "validate_plant_evidence", required_plants, gates["follow-up"].settings)
    gold, gold_refs = _parse_gold(root, raw["gold"], gates["follow-up"].kind)
    _run_kind_hook(gates, "validate_fixture_gold", gates["follow-up"].settings, gold)
    _validate_certification_gold(repeatability, gates["follow-up"].kind, gold)
    follow_up_artifact = _agent_artifact_reference(
        raw.get("follow_up_artifact"), "follow_up_artifact"
    )
    evidence_contract = followups.get(gates["follow-up"].kind).evidence_contract
    if evidence_contract and follow_up_artifact is None:
        raise ScenarioError(
            "follow_up_artifact is required for follow-up kind "
            f"{gates['follow-up'].kind!r}"
        )
    route_table = _parse_route_table(
        raw.get("route_table"),
        base_dir=root.resolve(),
        declared_source_tables=frozenset(getattr(get_dataset(dataset), "source_tables", ())),
    )
    script = OperatorScript.from_components(
        persona,
        answer_sheet,
        events=events,
        turns=answer_sheet.turns,
        turn_budget=turn_budget,
        sentinel=sentinel,
        obstacle_terms=obstacle_terms,
        phase_by_turn=phase_map,
        required_plants=required_plants,
    )
    return Scenario(
        package_dir=root.resolve(),
        scenario_id=scenario_id,
        run_order=run_order,
        tier=tier,
        fixture=fixture,
        coverage=coverage,
        turn_budget=turn_budget,
        repeatability=repeatability,
        persona_path=persona_path,
        persona=persona,
        answer_sheet_path=answer_sheet_path,
        answer_sheet=answer_sheet,
        events_path=events_path,
        events=events,
        phase_map=phase_map,
        required_plants=required_plants,
        gates=gates,
        gold=gold,
        gold_refs=gold_refs,
        operator_script=script,
        route_table=route_table,
        follow_up_artifact=follow_up_artifact,
    )


def load_scenarios(root: str | Path) -> tuple[Scenario, ...]:
    """Load every scenario package under a directory in declared run order.

    Run order is a declared field rather than a property of the directory name:
    the tier runs its scenarios in a fixed sequence, and encoding that sequence
    in a name prefix makes any rename silently reorder the tier.
    """

    directory = Path(root)
    if not directory.is_dir():
        raise ScenarioError(f"scenario root is not a directory: {directory}")
    declarations = sorted(path for path in directory.iterdir() if path.is_dir() and (path / "scenario.yaml").is_file())
    loaded = [load_scenario(path) for path in declarations]
    orders = [scenario.run_order for scenario in loaded]
    if len(set(orders)) != len(orders):
        raise ScenarioError("scenario run_order values must be unique within a root")
    return tuple(sorted(loaded, key=lambda scenario: scenario.run_order))


def select_tier(scenarios: Sequence[Scenario], tier: str) -> tuple[Scenario, ...]:
    """Return only the scenarios declaring ``tier``, preserving run order.

    ``load_scenarios`` deliberately loads every package under a root, and the
    tier a package declares was previously carried into the run manifest
    without ever selecting anything.  While every package was smoke that was
    invisible; the moment a core package shares the root it would ride along
    into the smoke tier, which is the one tier that must stay cheap enough to
    run on every change.  Selection is therefore explicit, and a tier that
    matches no package is an error rather than an empty, clean-looking run.
    """

    if tier not in _SCENARIO_TIERS:
        raise ScenarioError(f"unknown tier {tier!r}: expected one of {sorted(_SCENARIO_TIERS)}")
    # T0 is the legacy spelling of smoke -- manifest.py documents it as the
    # alias and the loader still accepts a package declaring it. Matching the
    # literal string would silently omit such a package from a smoke run
    # rather than reject it, and select_tier only raises when *nothing*
    # matches, so the omission would not surface at all.
    wanted = _TIER_ALIASES.get(tier, tier)
    selected = tuple(
        scenario for scenario in scenarios if _TIER_ALIASES.get(scenario.tier, scenario.tier) == wanted
    )
    if not selected:
        raise ScenarioError(f"no scenario declares tier {tier!r}")
    return selected


def _run_kind_hook(gates: Mapping[str, "GateSpec"], hook_name: str, *args: object) -> None:
    """Invoke one of a follow-up kind's optional loader hooks.

    These two checks -- required_plants against declared plant evidence, and
    fixture-gold internal consistency -- used to be functions in this module
    that returned early unless the kind was ``optional_required_outputs``.
    That left a new kind with no cross-validation at all, silently and by
    default, which is how a declared-but-ungraded gold artifact shipped once
    already. A kind now says what it wants checked; ``None`` still means "no
    cross-check", but it is a visible declaration in the kind's own module
    rather than an invisible early return here.
    """

    hook = getattr(followups.get(gates["follow-up"].kind), hook_name)
    if hook is not None:
        hook(*args)


def _validate_certification_gold(
    repeatability: RepeatabilitySpec,
    follow_up_kind: str,
    gold: Mapping[str, Path],
) -> None:
    """Reject certification claims whose scoreable gold is not declared."""

    required_gold = followups.get(follow_up_kind).certification_gold
    for gate in repeatability.gates:
        artifact = required_gold.get(gate)
        if artifact is not None and artifact not in gold:
            raise ScenarioError(
                f"certification gate {gate} requires scoreable gold artifact {artifact!r}"
            )


def _parse_route_table(
    value: object,
    *,
    base_dir: Path,
    declared_source_tables: frozenset[str],
) -> MockRouteTable | None:
    """Validate an optional inline mockrest route table at load time.

    Parsing (not merely storing) the mapping here means a malformed route
    table fails the same way every other scenario defect does -- at load,
    with a ``ScenarioError`` naming the problem -- rather than surfacing much
    later as an opaque ``ConfigError`` the first time a run tries to start
    the source.
    """

    if value is None:
        return None
    try:
        config = load_route_table(value, base_dir=base_dir)
        for table in sorted(fixture_source_tables(config)):
            if table not in declared_source_tables:
                raise ScenarioError(
                    f"route_table references fixture_source {table!r}, which is not "
                    "declared in fixture.dataset source_tables"
                )
        return config
    except ScenarioError:
        raise
    except MockRestConfigError as exc:
        raise ScenarioError(f"route_table is invalid: {exc}") from exc


def _naive_rows(value: object) -> list[dict[str, object]] | None:
    if not isinstance(value, Mapping):
        return None
    raw_regions = value.get("regions")
    if not isinstance(raw_regions, list):
        return None
    rows: list[dict[str, object]] = []
    for row in raw_regions:
        if not isinstance(row, Mapping) or not isinstance(row.get("region"), str) or not isinstance(row.get("naive_fanout_revenue"), (int, float)):
            return None
        rows.append({"region": row["region"], "regional_revenue": row["naive_fanout_revenue"]})
    return rows


__all__ = [
    "FixtureSpec",
    "GoldArtifactError",
    "GateSpec",
    "QueryAssessment",
    "RepeatabilitySpec",
    "Scenario",
    "ScenarioDeclaration",
    "ScenarioError",
    "declared_sentinels",
    "load_scenario",
    "SCENARIO_TIERS",
    "requires_live_session",
    "load_scenarios",
    "select_tier",
    "scenario_script_hash",
]

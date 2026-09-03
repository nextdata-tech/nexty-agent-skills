"""Declarative scenario packages and their fail-closed loader.

The invariant enforced here is that a runnable scenario contains every piece
of its fixture identity, operator script, planted difficulty, gate wiring, and
gold reference.  Keeping those values in package data makes a third scenario
addable without changing Python and prevents an omitted plant or answer file
from becoming an unmeasured pass.
"""

from __future__ import annotations

import csv
import hashlib
import json
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any

import yaml

from .grading import (
    GATE_PHASES,
    Finding,
    GoldRowSet,
    GateResult,
    gate_follow_up,
    gate_query,
    gold_rowset,
    sentinel_byte_scan,
)
from .grading.statistics import RepeatabilityTier, repeatability_plan
from .operator import EventSchedule, EventType, OperatorScript, PersonaCard, load_event_cards, load_persona
from .operator.answer_sheet import AnswerSheet, load_answer_sheet
from .synthgen import GenerationResult, generate_dataset, get_dataset


class ScenarioError(ValueError):
    """Raised when a scenario package is incomplete or internally inconsistent."""


_MISSING = object()


def _mapping(value: object, location: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ScenarioError(f"{location} must be a mapping")
    return dict(value)


def _unknown(value: Mapping[str, object], allowed: set[str], location: str) -> None:
    unknown = sorted(set(value) - allowed)
    if unknown:
        raise ScenarioError(f"{location} contains unknown key(s): {', '.join(unknown)}")


def _string(value: object, location: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ScenarioError(f"{location} must be a non-empty string")
    return value


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
            raise ScenarioError(f"generated gold artifact does not exist: {relative}")
        return path

    def load_gold(self, name: str = "answer", fixture_dir: str | Path | None = None) -> GoldRowSet:
        """Load a declared row-set through the deterministic EX scorer."""

        result = gold_rowset(self.gold_path(name, fixture_dir))
        if not result.passed or not isinstance(result.value, GoldRowSet):
            detail = result.findings[0].detail if result.findings else "gold row-set was not examined"
            raise ScenarioError(f"gold artifact {name!r} was rejected: {detail}")
        return result.value

    def raw_gold(self, name: str, fixture_dir: str | Path | None = None) -> object:
        """Read a declared JSON artifact after resolving its package path."""

        path = self.gold_path(name, fixture_dir)
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise ScenarioError(f"could not read gold artifact {name!r}: {exc}") from exc

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
        if isinstance(closure, Mapping) and (
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
        if binding.kind == "grain_and_aggregation":
            result: dict[str, object] = dict(_grain_follow_up(target, binding.settings))
        elif binding.kind == "optional_required_outputs":
            result = dict(
                self._zero_row_follow_up(
                    target,
                    binding.settings,
                    fixture_dir=fixture_dir if isinstance(fixture_dir, (str, Path)) else None,
                    row_count_oracle=row_count_oracle,
                )
            )
        elif binding.kind == "credential_rotation":
            result = dict(self._credential_rotation_follow_up(target, binding.settings))
        else:
            result = {"status": "not-examined", "passed": False, "findings": ["unknown_follow_up_kind"]}
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
        return result

    def follow_up_gate(
        self,
        closure: object,
        fixture_dir: str | Path | Sequence[Mapping[str, object]] | None = None,
        query_rows: Sequence[Mapping[str, object]] | None = None,
        *,
        fired_plants: object = _MISSING,
        row_count_oracle: object = _MISSING,
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
            ungraded=base.ungraded or result.get("status") in {"not-examined", "ungraded"},
        )

    def check_follow_up(
        self,
        closure: object,
        fixture_dir: str | Path | Sequence[Mapping[str, object]] | None = None,
        query_rows: Sequence[Mapping[str, object]] | None = None,
        *,
        fired_plants: object = _MISSING,
        row_count_oracle: object = _MISSING,
    ) -> GateResult:
        """Alias for callers that use the gate-oriented spelling."""

        return self.follow_up_gate(
            closure,
            fixture_dir,
            query_rows,
            fired_plants=fired_plants,
            row_count_oracle=row_count_oracle,
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

    def _credential_rotation_follow_up(
        self,
        target: object,
        settings: Mapping[str, object],
    ) -> Mapping[str, object]:
        """Grade the live-Postgres credential-rotation drill from supplied evidence.

        ``target`` is a mapping produced by the caller from a real
        ``PostgresFixture`` run (never the fixture's own narrative): a
        ``rotation_records`` sequence of ``{"step", "observations"}`` entries
        as returned by ``RotationRecord.to_dict()``, a ``surfaces`` mapping of
        transcript/log/error/closure byte surfaces for the marker-byte scan,
        and a ``diff`` mapping describing exactly which closure paths and
        attributes changed.  Every property is re-derived from that evidence;
        none of it is taken on the caller's word.
        """

        if not isinstance(target, Mapping):
            return {
                "status": "not-examined",
                "passed": False,
                "findings": ["credential_rotation_not_examined"],
            }

        records_raw = target.get("rotation_records")
        if (
            not isinstance(records_raw, Sequence)
            or isinstance(records_raw, (str, bytes, bytearray))
            or not records_raw
        ):
            return {
                "status": "not-examined",
                "passed": False,
                "findings": ["rotation_records_not_examined"],
            }
        records: dict[int, Mapping[str, object]] = {}
        for entry in records_raw:
            if not isinstance(entry, Mapping):
                return {
                    "status": "not-examined",
                    "passed": False,
                    "findings": ["rotation_records_not_examined"],
                }
            step = entry.get("step")
            observations = entry.get("observations")
            if (
                isinstance(step, bool)
                or not isinstance(step, int)
                or not isinstance(observations, Mapping)
            ):
                return {
                    "status": "not-examined",
                    "passed": False,
                    "findings": ["rotation_records_not_examined"],
                }
            records[step] = observations

        findings: list[str] = []
        if {0, 1, 2} - set(records):
            findings.append("rotation_records_incomplete")

        # Constraint: information_schema hides the lookup schema, but
        # pg_catalog.pg_namespace/pg_class are readable by PUBLIC.  A record
        # that reports the schema as unconditionally invisible is wrong, and
        # is exactly the false claim a prior version of this fixture made.
        # Step 2's observation keys are prefixed "new_credential_" (they
        # describe the freshly issued credential, not the role generically);
        # every other step uses the unprefixed names.
        for step, observations in sorted(records.items()):
            prefix = "new_credential_" if step == 2 else ""
            # Both catalog probes are graded.  ``pg_class`` carries the table
            # and ``pg_namespace`` carries the schema; the round-1 review
            # finding this fixture exists to prevent was specifically that
            # pg_namespace is PUBLIC-readable, so a record claiming the schema
            # is invisible is wrong.  Grading only the relation probe would
            # leave the namespace claim unchecked.
            relations_visible = observations.get(f"{prefix}lookup_relations_catalog_visible")
            namespace_visible = observations.get(f"{prefix}lookup_catalog_visible")
            info_schema_visible = observations.get(f"{prefix}lookup_information_schema_visible")
            if (
                relations_visible is not True
                or namespace_visible is not True
                or info_schema_visible is not False
            ):
                findings.append(f"catalog_visibility_property_violated:{step}")
            # Least privilege is the load-bearing property, not merely the
            # visibility split: the lookup schema stays unreadable at every
            # step, including after the rotation re-grants inventory access.
            # A rotation that silently widened the role's grants would
            # otherwise pass this gate clean.
            if observations.get(f"{prefix}lookup_query_denied") is not True:
                findings.append(f"lookup_schema_readable_at_step:{step}")

        step1 = records.get(1)
        if step1 is not None:
            if step1.get("login_succeeds") is not True:
                findings.append("step1_login_unexpectedly_lost")
            if step1.get("inventory_query_succeeds") is not False:
                findings.append("step1_select_not_revoked")

        step2 = records.get(2)
        if step2 is not None:
            # Constraint: the rotation must not be bypassable.  The old
            # credential must no longer authenticate at all once rotated; a
            # prior version handed the evaluation role the superuser
            # password, so this is checked directly rather than trusted.
            if step2.get("old_credential_login_succeeds") is not False:
                findings.append("rotation_bypassable_old_credential_still_authenticates")
            if step2.get("new_credential_inventory_query_succeeds") is not True:
                findings.append("rotation_left_new_credential_unusable")

        # The marker is the real sentinel carried by this scenario's own
        # scripted credential_fumble event card, never a value invented here,
        # so the scan is checked against exactly what the operator "pasted".
        markers = tuple(
            card.sentinel
            for card in self.events.cards
            if card.event_type is EventType.CREDENTIAL_FUMBLE and card.sentinel
        )
        surfaces = target.get("surfaces")
        if not markers:
            findings.append("secret_hygiene_not_examined")
        elif not isinstance(surfaces, Mapping) or not surfaces:
            findings.append("secret_hygiene_not_examined")
        else:
            scan = sentinel_byte_scan(surfaces, markers)
            if not scan.examined:
                findings.append("secret_hygiene_not_examined")
            elif not scan.passed:
                findings.append("secret_marker_leaked")

        # The declared diagnostics gold is graded, not merely shipped: B5's
        # pass criterion is that orphans and negative quantities are reported
        # as data rather than cleaned away, so the counts the run reports are
        # compared against the committed gold.
        expected_diagnostics = self.raw_gold("diagnostics")
        reported = target.get("diagnostics")
        if not isinstance(expected_diagnostics, Mapping):
            findings.append("diagnostics_gold_unreadable")
        elif not isinstance(reported, Mapping):
            findings.append("diagnostics_not_examined")
        else:
            for key in ("orphan_line_item_count", "negative_quantity_count"):
                expected = expected_diagnostics.get(key)
                actual = reported.get(key)
                if isinstance(actual, bool) or not isinstance(actual, int):
                    findings.append(f"diagnostics_not_examined:{key}")
                elif actual != expected:
                    findings.append(f"diagnostics_disagree_with_gold:{key}")

        allowed_path = _string(settings.get("allowed_diff_path"), "follow-up.allowed_diff_path")
        allowed_attribute = _string(
            settings.get("allowed_diff_attribute"), "follow-up.allowed_diff_attribute"
        )
        diff = target.get("diff")
        if not isinstance(diff, Mapping):
            findings.append("diff_not_examined")
        else:
            changed_paths = diff.get("changed_paths")
            changed_attributes = diff.get("changed_attributes")
            if not isinstance(changed_paths, Sequence) or isinstance(
                changed_paths, (str, bytes, bytearray)
            ):
                findings.append("diff_not_examined")
            else:
                other_paths = sorted({path for path in changed_paths if path != allowed_path})
                if other_paths:
                    findings.append("diff_touches_non_credential_files")
                if not isinstance(changed_attributes, Sequence) or isinstance(
                    changed_attributes, (str, bytes, bytearray)
                ):
                    findings.append("diff_not_examined")
                elif list(changed_attributes) != [allowed_attribute]:
                    findings.append("diff_not_confined_to_credential_attribute")

        return {"status": "examined", "passed": not findings, "findings": findings}

    def _zero_row_follow_up(
        self,
        target: object,
        settings: Mapping[str, object],
        *,
        fixture_dir: str | Path | None = None,
        row_count_oracle: object = _MISSING,
    ) -> Mapping[str, object]:
        resources = _mapping(settings.get("resources"), "follow-up.resources")
        declared_required = {
            resource: _required_flag(value, f"follow-up.resources.{resource}")
            for resource, value in resources.items()
        }
        findings: list[str] = []

        closure_target = target
        if isinstance(target, Mapping) and "closure" in target:
            closure_target = target.get("closure")
            if row_count_oracle is _MISSING:
                row_count_oracle = target.get("row_count_oracle", target.get("row_counts", _MISSING))

        requiredness_document = _read_document(
            closure_target,
            _string(settings.get("document"), "follow-up.document"),
        )
        observed_required = _requiredness_from_document(
            requiredness_document,
            _string(settings.get("requiredness_path"), "follow-up.requiredness_path"),
        )
        if observed_required is None:
            return {
                "status": "not-examined",
                "passed": False,
                "findings": ["requiredness_not_examined"],
            }
        if observed_required != declared_required:
            findings.append("requiredness_artifact_mismatch")

        count_source = "not-examined"
        actual_counts: dict[str, int] | None = None
        malformed_resources: set[str] = set()
        if row_count_oracle is not _MISSING:
            count_source = "row_count_oracle"
            actual_counts = _row_count_mapping(row_count_oracle)
            if actual_counts is None:
                return {
                    "status": "not-examined",
                    "passed": False,
                    "findings": ["resource_counts_not_examined"],
                }
        elif isinstance(fixture_dir, (str, Path)):
            manifest = _read_document(fixture_dir, "fixture-manifest.json")
            actual_counts = _manifest_row_counts(manifest)
            if actual_counts is None:
                count_source = "closure_data"
            else:
                count_source = "fixture_manifest"
        elif isinstance(closure_target, Mapping):
            # Preserve the direct mapping API as an explicit oracle input.
            actual_counts = _row_count_mapping(closure_target)
            if actual_counts is None:
                count_source = "closure_data"
        if actual_counts is None and isinstance(closure_target, (str, Path)):
            count_source = "closure_data"
            root = Path(closure_target)
            data_root = root / "data"
            if not root.is_dir() or not data_root.is_dir():
                return {
                    "status": "not-examined",
                    "passed": False,
                    "findings": ["resource_counts_not_examined"],
                }
            actual_counts = {}
            for resource in resources:
                path = data_root / f"{resource}.csv"
                if not path.is_file():
                    continue
                try:
                    with path.open(encoding="utf-8", newline="") as handle:
                        reader = csv.DictReader(handle)
                        if not reader.fieldnames or any(
                            not isinstance(field, str) or not field.strip() for field in reader.fieldnames
                        ):
                            malformed_resources.add(resource)
                            continue
                        actual_counts[resource] = sum(1 for _ in reader)
                except (OSError, UnicodeError, csv.Error):
                    malformed_resources.add(resource)
            findings.extend(f"resource_malformed:{resource}" for resource in sorted(malformed_resources))
        if actual_counts is None:
            return {"status": "not-examined", "passed": False, "findings": ["resource_counts_not_examined"]}

        expected_counts = _count_rows(self.raw_gold("counts", fixture_dir))
        for resource, required in declared_required.items():
            if resource not in actual_counts:
                if resource in malformed_resources:
                    continue
                if required is False:
                    findings.append("optional_resource_absent")
                else:
                    findings.append("required_resource_absent")
        if actual_counts != expected_counts:
            findings.append("resource_count_mismatch")
        optional = [resource for resource, required in declared_required.items() if required is False]
        if any(resource in actual_counts and actual_counts[resource] != 0 for resource in optional):
            findings.append("optional_placeholder_row")
        return {
            "status": "examined",
            "passed": not findings,
            "findings": findings,
            "actual_counts": actual_counts,
            "expected_counts": expected_counts,
            "required": declared_required,
            "observed_required": observed_required,
            "count_source": count_source,
        }


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
_FIXTURE_KEYS = {"dataset", "seed", "variant", "plant"}
_REPEATABILITY_KEYS = {"tier", "epochs", "certification"}
_CERTIFICATION_KEYS = {"rule", "gates", "lower_bound", "confidence"}
_OPERATOR_KEYS = {"sentinel", "obstacle_terms"}
_COVERAGE_KEYS = {"variant", "untested"}
_SCENARIO_TIERS = frozenset({"smoke", "T0", "core"})
_DATASET_PLANT_DECLARATIONS = {
    "grain_trap": "grain_trap_fanout",
    "zero_row_optional": "optional_zero_row",
}
_GOLD_KEYS_BY_FOLLOW_UP = {
    "grain_and_aggregation": frozenset({"answer", "control_total", "diagnostics"}),
    "optional_required_outputs": frozenset({"counts", "diagnostics"}),
    "credential_rotation": frozenset({"diagnostics"}),
}
_CERTIFICATION_GOLD_BY_FOLLOW_UP = {
    "optional_required_outputs": {"build": "counts", "query": "answer"},
    "grain_and_aggregation": {"query": "answer"},
}


def _canonical_hash(value: object) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _is_row_sequence(value: object) -> bool:
    return isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)) and all(
        isinstance(row, Mapping) for row in value
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
    declared_plant = _DATASET_PLANT_DECLARATIONS.get(dataset)
    if declared_plant is None:
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


def _validate_plant_evidence(required: frozenset[str], gates: Mapping[str, GateSpec]) -> None:
    if gates["follow-up"].kind != "optional_required_outputs":
        return
    raw = gates["follow-up"].settings.get("plant_evidence")
    evidence = _mapping(raw, "follow-up.plant_evidence")
    missing = sorted(required - set(evidence))
    if missing:
        raise ScenarioError("follow-up.plant_evidence is missing required plant(s): " + ", ".join(missing))
    unknown = sorted(set(evidence) - required)
    if unknown:
        raise ScenarioError("follow-up.plant_evidence contains unknown plant(s): " + ", ".join(unknown))


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
    if parsed["follow-up"].kind not in {
        "grain_and_aggregation",
        "optional_required_outputs",
        "credential_rotation",
    }:
        raise ScenarioError("gates.follow-up must declare a supported scenario-specific follow-up")
    if parsed["follow-up"].kind == "credential_rotation":
        settings = parsed["follow-up"].settings
        _string(settings.get("allowed_diff_path"), "follow-up.allowed_diff_path")
        _string(settings.get("allowed_diff_attribute"), "follow-up.allowed_diff_attribute")
    if parsed["follow-up"].kind == "grain_and_aggregation":
        _string(parsed["follow-up"].settings.get("document"), "gates.follow-up.document")
    if parsed["follow-up"].kind == "optional_required_outputs":
        settings = parsed["follow-up"].settings
        if settings.get("count_source") != "row_count_oracle":
            raise ScenarioError("follow-up.count_source must be row_count_oracle")
        _string(settings.get("document"), "follow-up.document")
        _string(settings.get("requiredness_path"), "follow-up.requiredness_path")
        resources = _mapping(settings.get("resources"), "follow-up.resources")
        for resource, declaration in resources.items():
            _required_flag(declaration, f"follow-up.resources.{resource}")
        plant_evidence = _mapping(settings.get("plant_evidence"), "follow-up.plant_evidence")
        for plant, declaration in plant_evidence.items():
            evidence = _mapping(declaration, f"follow-up.plant_evidence.{plant}")
            _string(evidence.get("resource"), f"follow-up.plant_evidence.{plant}.resource")
            row_count = evidence.get("row_count")
            if isinstance(row_count, bool) or not isinstance(row_count, int) or row_count < 0:
                raise ScenarioError(f"follow-up.plant_evidence.{plant}.row_count must be a non-negative integer")
    return MappingProxyType(parsed)


def _parse_gold(
    root: Path,
    value: object,
    follow_up_kind: str,
) -> tuple[Mapping[str, Path], Mapping[str, str]]:
    raw = _mapping(value, "gold")
    expected = _GOLD_KEYS_BY_FOLLOW_UP[follow_up_kind]
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
    _unknown(raw, _SCENARIO_KEYS, "scenario")
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
        if dataset == "zero_row_optional":
            raise ScenarioError("fixture requires dataset, seed, variant, and plant")
        explicit_plant = _DATASET_PLANT_DECLARATIONS.get(dataset)
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
    _validate_plant_evidence(required_plants, gates)
    gold, gold_refs = _parse_gold(root, raw["gold"], gates["follow-up"].kind)
    _validate_fixture_gold(gates["follow-up"].kind, gates["follow-up"].settings, gold)
    _validate_certification_gold(repeatability, gates["follow-up"].kind, gold)
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
    selected = tuple(scenario for scenario in scenarios if scenario.tier == tier)
    if not selected:
        raise ScenarioError(f"no scenario declares tier {tier!r}")
    return selected


def _read_document(value: object, document_name: str | None = None) -> object:
    if isinstance(value, Mapping):
        return value
    path = Path(value) if isinstance(value, (str, Path)) else None
    if path is None or not path.exists():
        return _MISSING
    if path.is_file():
        candidates = [path]
    elif document_name is not None:
        document = Path(document_name)
        if document.is_absolute() or ".." in document.parts:
            return _MISSING
        candidates = [path / document]
    else:
        return _MISSING
    candidates = [candidate for candidate in candidates if candidate.is_file()]
    documents: list[Mapping[str, object]] = []
    for candidate in candidates:
        try:
            parsed = json.loads(candidate.read_text(encoding="utf-8")) if candidate.suffix.lower() == ".json" else yaml.safe_load(candidate.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError, yaml.YAMLError):
            continue
        if isinstance(parsed, Mapping):
            documents.append(dict(parsed))
    if not documents:
        return _MISSING
    merged: dict[str, object] = {}
    for document in documents:
        merged.update(document)
    return merged


def _lookup(value: object, dotted_path: str) -> object:
    current = value
    for part in dotted_path.split("."):
        if not isinstance(current, Mapping) or part not in current:
            return _MISSING
        current = current[part]
    return current


def _grain_follow_up(closure: object, settings: Mapping[str, object]) -> Mapping[str, object]:
    document = _read_document(closure, _string(settings.get("document"), "follow-up.document"))
    if document is _MISSING:
        return {"status": "not-examined", "passed": False, "findings": ["closure_not_examined"]}
    grain_path = _string(settings.get("grain_path"), "follow-up.grain_path")
    aggregation_path = _string(settings.get("aggregation_path"), "follow-up.aggregation_path")
    expected_grain = _string(settings.get("expected_grain"), "follow-up.expected_grain")
    expected_aggregation = _string(settings.get("expected_aggregation"), "follow-up.expected_aggregation")
    observed_grain = _lookup(document, grain_path)
    observed_aggregation = _lookup(document, aggregation_path)
    findings: list[str] = []
    if observed_grain is _MISSING:
        findings.append("grain_not_declared")
    elif observed_grain != expected_grain:
        findings.append("grain_mismatch")
    if observed_aggregation is _MISSING:
        findings.append("aggregation_not_declared")
    elif observed_aggregation != expected_aggregation:
        findings.append("aggregation_mismatch")
    return {
        "status": "examined",
        "passed": not findings,
        "findings": findings,
        "grain": observed_grain if observed_grain is not _MISSING else None,
        "aggregation": observed_aggregation if observed_aggregation is not _MISSING else None,
    }


def _required_flag(value: object, location: str) -> bool:
    declaration = _mapping(value, location)
    required = declaration.get("required")
    if not isinstance(required, bool):
        raise ScenarioError(f"{location}.required must be boolean")
    return required


def _declared_required(settings: Mapping[str, object]) -> dict[str, bool]:
    resources = _mapping(settings.get("resources"), "follow-up.resources")
    return {
        str(resource): _required_flag(value, f"follow-up.resources.{resource}")
        for resource, value in resources.items()
    }


def _requiredness_from_document(document: object, path: str) -> dict[str, bool] | None:
    if document is _MISSING:
        return None
    raw = _lookup(document, path)
    if not isinstance(raw, Mapping) or not raw:
        return None
    result: dict[str, bool] = {}
    for resource, value in raw.items():
        if not isinstance(resource, str):
            return None
        if isinstance(value, bool):
            result[resource] = value
            continue
        if isinstance(value, Mapping) and isinstance(value.get("required"), bool):
            result[resource] = value["required"]
            continue
        return None
    return result


def _row_count_mapping(value: object) -> dict[str, int] | None:
    if not isinstance(value, Mapping):
        return None
    candidate: object = value
    for key in ("row_count_oracle", "per_model_row_counts", "row_counts", "counts"):
        nested = value.get(key)
        if isinstance(nested, Mapping):
            candidate = nested
            break
    if not isinstance(candidate, Mapping) or not candidate:
        return None
    result: dict[str, int] = {}
    for resource, count in candidate.items():
        if (
            not isinstance(resource, str)
            or isinstance(count, bool)
            or not isinstance(count, int)
            or count < 0
        ):
            return None
        result[resource] = count
    return result


def _manifest_row_counts(manifest: object) -> dict[str, int] | None:
    if isinstance(manifest, Mapping):
        table_counts = manifest.get("table_row_counts")
        if isinstance(table_counts, Mapping):
            return _row_count_mapping(table_counts)
    return _row_count_mapping(manifest)


def _validate_fixture_gold(
    follow_up_kind: str,
    settings: Mapping[str, object],
    gold: Mapping[str, Path],
) -> None:
    """Validate fixture-side consistency before any run can be graded."""

    if follow_up_kind != "optional_required_outputs":
        return
    try:
        counts = json.loads(gold["counts"].read_text(encoding="utf-8"))
        diagnostics = json.loads(gold["diagnostics"].read_text(encoding="utf-8"))
        expected_counts = _count_rows(counts)
        expected_diagnostics = _diagnostic_rows(diagnostics)
    except (KeyError, OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ScenarioError(f"optional-output gold could not be loaded: {exc}") from exc
    expected_required = {
        row["resource"]: row["required"] for row in expected_diagnostics
    }
    if _declared_required(settings) != expected_required:
        raise ScenarioError("optional-output diagnostics gold requiredness disagrees with follow-up.resources")
    if set(expected_counts) != set(expected_required):
        raise ScenarioError("optional-output count and diagnostics gold resource sets disagree")


def _validate_certification_gold(
    repeatability: RepeatabilitySpec,
    follow_up_kind: str,
    gold: Mapping[str, Path],
) -> None:
    """Reject certification claims whose scoreable gold is not declared."""

    required_gold = _CERTIFICATION_GOLD_BY_FOLLOW_UP.get(follow_up_kind, {})
    for gate in repeatability.gates:
        artifact = required_gold.get(gate)
        if artifact is not None and artifact not in gold:
            raise ScenarioError(
                f"certification gate {gate} requires scoreable gold artifact {artifact!r}"
            )


def _count_rows(value: object) -> dict[str, int]:
    if not isinstance(value, list):
        raise ScenarioError("count gold must be a list of rows")
    result: dict[str, int] = {}
    for row in value:
        if (
            not isinstance(row, Mapping)
            or not isinstance(row.get("resource"), str)
            or isinstance(row.get("row_count"), bool)
            or not isinstance(row.get("row_count"), int)
            or row["row_count"] < 0
        ):
            raise ScenarioError("count gold rows require resource and integer row_count")
        result[row["resource"]] = row["row_count"]
    return result


def _diagnostic_rows(value: object) -> list[dict[str, object]]:
    if not isinstance(value, list):
        raise ScenarioError("diagnostic gold must be a list of rows")
    result: list[dict[str, object]] = []
    for row in value:
        if (
            not isinstance(row, Mapping)
            or not isinstance(row.get("resource"), str)
            or isinstance(row.get("row_count"), bool)
            or not isinstance(row.get("row_count"), int)
            or row["row_count"] < 0
            or not isinstance(row.get("required"), bool)
        ):
            raise ScenarioError("diagnostic gold rows require resource, integer row_count, and boolean required")
        result.append(dict(row))
    return result


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
    "GateSpec",
    "QueryAssessment",
    "RepeatabilitySpec",
    "Scenario",
    "ScenarioDeclaration",
    "ScenarioError",
    "load_scenario",
    "load_scenarios",
    "select_tier",
    "scenario_script_hash",
]

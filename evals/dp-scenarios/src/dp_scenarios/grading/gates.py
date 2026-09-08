"""Mechanical phase gates over closed run artifacts.

The invariant enforced here is that a gate can only use an artifact that owns
the fact being checked.  In particular, ledger ordering, supervisor counts,
and query rows are never recovered from an operator's prose.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from dp_scenarios.ledger import lint as ledger_lint
from dp_scenarios.ledger import read_ledger
from dp_scenarios.ledger.lint import Finding as LintFinding
from dp_scenarios.ledger.lint import LintReport
from dp_scenarios.ledger.schema import ACTION_KINDS


@dataclass(frozen=True, slots=True)
class Finding:
    """One stable machine-readable gate finding."""

    code: str
    detail: str = ""
    value: object = None


@dataclass(frozen=True, slots=True)
class GateResult:
    """A gate result whose awarded points are independent of efficiency."""

    gate: str
    passed: bool
    points: int
    findings: tuple[Finding, ...] = ()
    examined: bool = True
    ungraded: bool = False
    required: bool = True
    diagnostics: tuple[Finding, ...] = ()

    @property
    def codes(self) -> tuple[str, ...]:
        """Return finding codes in stable order."""

        return tuple(finding.code for finding in self.findings)


# The protocol phase each gate is graded in.  This used to be implicit in the
# gate's own name, which meant a rename could silently break reachability
# checking; naming it makes the coupling checkable.
GATE_PHASES: Mapping[str, int] = {
    "intake": 1,
    "capability": 2,
    "narrowing": 3,
    "construction": 4,
    "build": 5,
    "query": 6,
    "follow-up": 7,
}


LEGACY_GATE_ALIASES: Mapping[str, str] = {
    "G1": "intake",
    "G2": "capability",
    "G3": "narrowing",
    "G4": "construction",
    "G5": "build",
    "G6": "query",
    "G7": "follow-up",
    "g1_intake": "intake",
    "g2_capability": "capability",
    "g3_narrowing": "narrowing",
    "g4_construction": "construction",
    "g5_build": "build",
    "g6_query": "query",
    "g7_follow_up": "follow-up",
}


class _GatePoints(dict[str, int]):
    """Canonical points with read compatibility for the former G1-G7 keys."""

    def __getitem__(self, key: str) -> int:
        return super().__getitem__(LEGACY_GATE_ALIASES.get(key, key))

    def get(self, key: str, default: int | None = None) -> int | None:
        return super().get(LEGACY_GATE_ALIASES.get(key, key), default)

    def __contains__(self, key: object) -> bool:
        return super().__contains__(LEGACY_GATE_ALIASES.get(key, key) if isinstance(key, str) else key)


GATE_POINTS: Mapping[str, int] = _GatePoints({
    "intake": 10,
    "capability": 15,
    "narrowing": 10,
    "construction": 10,
    "build": 20,
    "query": 20,
    "follow-up": 15,
})


NOT_STAGED_CODES = frozenset({
    "capability_shortfall_not_staged",
    "narrowing_change_not_staged",
    # Decided the same way -- from `"answer" in scenario.gold`, read at load
    # time -- and already required=False. Rendering it as UNEXAMINED said the
    # harness could not look, when the truth is that the scenario does not
    # stage a scoreable answer.
    "query_answer_gold_not_declared",
})


def _rows(value: object) -> list[Mapping[str, object]]:
    """Coerce a ledger artifact without accepting an arbitrary text account."""

    if isinstance(value, (str, Path)):
        return [row for row in read_ledger(value) if isinstance(row, Mapping)]
    if isinstance(value, Mapping):
        candidate = value.get("rows", value.get("ledger", ()))
        if isinstance(candidate, Mapping):
            candidate = candidate.get("rows", ())
        if isinstance(candidate, Sequence) and not isinstance(candidate, (str, bytes, bytearray)):
            return [row for row in candidate if isinstance(row, Mapping)]
        return [value] if value else []
    if isinstance(value, Iterable):
        return [row for row in value if isinstance(row, Mapping)]
    raise TypeError("ledger artifact must be a path, mapping, or row sequence")


def _result(
    gate: str,
    passed: bool,
    findings: Iterable[Finding] = (),
    *,
    examined: bool = True,
    ungraded: bool = False,
    required: bool = True,
    diagnostics: Iterable[Finding] = (),
) -> GateResult:
    finding_tuple = tuple(findings)
    return GateResult(
        gate=gate,
        passed=passed and not finding_tuple,
        points=GATE_POINTS[gate] if passed and not finding_tuple else 0,
        findings=finding_tuple,
        examined=examined,
        ungraded=ungraded,
        required=required,
        diagnostics=tuple(diagnostics),
    )


CLOSURE_DIR = "closure"


def _authored_closure(files: object) -> bool:
    """Report whether a turn wrote into the authored data-product closure.

    This is the only observational evidence ``gate_intake`` accepts as
    codegen, and the asymmetry is deliberate.  The inference feeds two
    checks at once: it can supply a codegen turn the ledger failed to record,
    and it can trip ``intake_approval_not_before_codegen``.  Because of the
    second role, a false positive does not merely weaken a check -- it makes
    the gate unpassable for every run.  A false negative only falls back to
    the ledger's own ``codegen`` row, which is the authoritative signal
    anyway.  So this errs toward not inferring.

    Counts as codegen: a touched path with a ``closure`` component, which the
    live adapter's system prompt makes the contractual home of the authored
    data product.  Because the live adapter derives ``files_touched`` from a
    workspace diff rather than from tool names, this catches a closure write
    however it was performed -- Write, Edit, a Bash heredoc, or an MCP build
    tool alike.

    Deliberately does not count: tool calls of any name, including writes.
    A tool name cannot distinguish authoring the closure from authoring the
    blueprint, and the blueprint is what an agent is *supposed* to write
    before asking for approval.  Reading a config file, listing data
    products, or probing a source is likewise pre-approval work, not
    codegen.  Touched files outside the closure do not count either, for the
    same reason: the live workspace diff includes the root-level
    ``dp-blueprint.md``/``dp-spec.md`` that exists precisely to be approved.

    A malformed entry is not treated as authoring.  Fail-closed would mean
    inferring codegen here, which is the failure mode this guards against.
    """

    if not isinstance(files, Sequence) or isinstance(files, (str, bytes, bytearray)):
        return False
    for file in files:
        path = file.get("path") if isinstance(file, Mapping) else file
        if isinstance(path, Path):
            path = path.as_posix()
        if not isinstance(path, str):
            continue
        if CLOSURE_DIR in PurePosixPath(path.replace("\\", "/")).parts:
            return True
    return False


def gate_intake(ledger: object) -> GateResult:
    """intake: require approval strictly before the first code-generation row."""

    rows = _rows(ledger)
    if not rows:
        return _result(
            "intake",
            False,
            [Finding("intake_ledger_not_examined", "ledger contains no rows")],
            examined=False,
        )
    approvals = [row["turn"] for row in rows if row.get("action_kind") == "spec_approved" and isinstance(row.get("turn"), int)]
    codegen = [row["turn"] for row in rows if row.get("action_kind") == "codegen" and isinstance(row.get("turn"), int)]
    if isinstance(ledger, Mapping):
        observations = ledger.get("observations")
        if isinstance(observations, Mapping):
            turns = observations.get("turns")
            if isinstance(turns, Sequence) and not isinstance(turns, (str, bytes, bytearray)):
                for turn in turns:
                    if not isinstance(turn, Mapping) or not isinstance(turn.get("turn"), int):
                        continue
                    if _authored_closure(turn.get("files_touched")):
                        codegen.append(turn["turn"])
    findings: list[Finding] = []
    for row in rows:
        action_kind = row.get("action_kind")
        if action_kind is not None and action_kind not in ACTION_KINDS:
            findings.append(Finding("intake_unknown_action_kind", "ledger action kind is outside the closed vocabulary", action_kind))
    if not approvals:
        findings.append(Finding("intake_spec_approval_missing", "no spec approval row is recorded"))
    if not codegen:
        findings.append(Finding("intake_codegen_missing", "no codegen row is recorded"))
    # Codegen may not start on a turn *earlier* than the approval, but it may
    # start on the same one. An operator approval is transmitted at the top of
    # a turn and the agent's response to it is the rest of that same turn, so
    # authoring immediately after being told "approved, go ahead" lands on the
    # approval's own turn number. Requiring a strictly later turn failed the
    # agent for doing exactly the right thing, which a live run demonstrated:
    # spec_approved and the first closure write were both recorded at turn 4.
    if approvals and codegen and min(codegen) < min(approvals):
        findings.append(Finding("intake_approval_not_before_codegen", "codegen turn precedes the approval", {"approval": min(approvals), "codegen": min(codegen)}))
    return _result("intake", not findings, findings)


def _metric_labels(spec: object) -> dict[str, str]:
    if isinstance(spec, Mapping):
        raw = spec.get("metrics", spec.get("metric_labels", spec))
    else:
        raw = spec
    result: dict[str, str] = {}
    if isinstance(raw, Mapping):
        for name, label in raw.items():
            if isinstance(label, Mapping):
                value = label.get("classification", label.get("label", label.get("support")))
            else:
                value = label
            if isinstance(name, str) and isinstance(value, str):
                result[name] = value
    elif isinstance(raw, Sequence) and not isinstance(raw, (str, bytes, bytearray)):
        for item in raw:
            if isinstance(item, Mapping):
                name = item.get("name", item.get("metric"))
                label = item.get("classification", item.get("label", item.get("support")))
                if isinstance(name, str) and isinstance(label, str):
                    result[name] = label
    return result


def _capability_labels(capability: object) -> Mapping[str, str]:
    if hasattr(capability, "metrics"):
        value = getattr(capability, "metrics")
    elif isinstance(capability, Mapping):
        value = capability.get("metrics", capability)
    else:
        value = {}
    return value if isinstance(value, Mapping) else {}


def _decision_rows(decisions: object) -> tuple[Mapping[str, str], ...]:
    """Return governed decision rows, whatever shape the loader produced."""

    if isinstance(decisions, Mapping):
        rows = decisions.get("rows", decisions.get("decisions"))
    else:
        rows = decisions
    if not isinstance(rows, (list, tuple)):
        return ()
    return tuple(row for row in rows if isinstance(row, Mapping))


def _metric_is_implemented(terms: Sequence[str], implementation: str) -> bool:
    lowered = implementation.lower()
    return any(term.lower() in lowered for term in terms if isinstance(term, str) and term)


# The vocabularies below mirror ``LEDGER_VOCAB`` in
# ``src/nxd-run-job-loop/scripts/self_check.py`` (phase D), which is the source
# of truth and hard-fails a closure whose ledger leaves them.  They are copied
# rather than imported because the harness cannot import the shipped helper;
# keep them in step with that file, not with whatever a run happened to emit.
_LEDGER_STATUS = frozenset({"confirmed", "proposed", "blocked"})
_LEDGER_PROVENANCE = frozenset(
    {"user_confirmed", "agent_authored", "source_derived", "deferred"}
)
#: Columns a ruling needs to be readable as one: ``applies_to`` is the field
#: that *binds* a ruling to columns, and without it there is nothing to grade
#: governance against except prose.
_LEDGER_COLUMNS = ("status", "provenance", "applies_to")
#: ``blocked`` is in the ledger vocabulary but governs nothing: it records a
#: deferral with no model behind it.  Derived rather than written out again so
#: a future addition to phase D's ``LEDGER_VOCAB`` lands in one place.
_GOVERNING_STATUS = _LEDGER_STATUS - {"blocked"}


def _ledger_contract_breaches(rows: Sequence[Mapping[str, str]]) -> tuple[str, ...]:
    """Return why a non-empty decision ledger is not gradeable, or ``()``.

    An empty or absent ledger is *not* off-contract -- it is simply a closure
    with no rulings, which the per-metric loop already grades correctly.  Only a
    ledger that has rows and still cannot be read as rulings lands here.
    """

    if not rows:
        return ()
    present = set(rows[0])
    breaches = [
        f"no {column!r} column" for column in _LEDGER_COLUMNS if column not in present
    ]
    for column, vocabulary in (("status", _LEDGER_STATUS), ("provenance", _LEDGER_PROVENANCE)):
        if column not in present:
            continue
        # Union every row's value, as phase D does: one out-of-vocabulary row
        # among clean ones still makes the ledger unreadable as a class, and
        # dropping it would let the survivors quietly govern in its place.
        unknown = {str(row.get(column, "")).strip().lower() for row in rows} - vocabulary
        if unknown:
            breaches.append(f"{column} has {sorted(unknown)}")
    return tuple(breaches)


def _metric_is_governed(terms: Sequence[str], rows: Sequence[Mapping[str, str]]) -> bool:
    """Whether a governing decision row covers any of a metric's column terms.

    Callers must have cleared ``_ledger_contract_breaches`` first: a row without
    ``applies_to`` never reaches here, so there is no temptation to fall back to
    matching ``description`` or any other prose field.
    """

    for row in rows:
        # ``proposed`` is the documented landing state for an agent-authored
        # ruling: `nxd-generate-data-product/reference/llm-judgments.md` says
        # rows land `proposed` + `agent_authored` and become `confirmed` only
        # once a user reviews them. Requiring `confirmed` graded the user's
        # review, not the agent's governance, and failed an agent that followed
        # the pack's own default. ``blocked`` does not govern anything: it
        # records a deferral with no model behind it.
        if str(row.get("status", "")).strip().lower() not in _GOVERNING_STATUS:
            continue
        # Bind on the fields that *bind* -- not on free prose. Matching `ruling`
        # and `detail` meant any confirmed row merely mentioning a term governed
        # the metric, so "pipeline velocity is out of scope" would mark
        # stage_velocity_30d governed and turn a real ungoverned shortfall into
        # a pass.
        blob = " ".join(str(row.get(field, "")) for field in ("applies_to", "decision_id")).lower()
        if any(term.lower() in blob for term in terms if isinstance(term, str) and term):
            return True
    return False


def _capability_metric_terms(capability: object) -> dict[str, tuple[str, ...]]:
    """Return the fixture's metric -> column-term map, if it declares one.

    The mapping lives in the fixture rather than in the gate because it is
    scenario knowledge: only ``capability-shortfall``'s gold knows that
    ``time_in_stage_days`` is what a ``stage_age_days`` column implements.
    Keeping it declared also keeps the gate model-free -- it is a substring
    test against names the fixture chose, not an inference about meaning.
    """

    if not isinstance(capability, Mapping):
        return {}
    raw = capability.get("metric_terms")
    if not isinstance(raw, Mapping):
        return {}
    terms: dict[str, tuple[str, ...]] = {}
    for name, value in raw.items():
        if isinstance(value, str):
            value = (value,)
        if isinstance(value, (list, tuple)):
            cleaned = tuple(item for item in value if isinstance(item, str) and item.strip())
            if cleaned:
                terms[str(name)] = cleaned
    return terms


def gate_capability_from_decisions(
    decisions: object,
    capability: object,
    implementation: str | None,
    *,
    required: bool = True,
) -> GateResult:
    """capability: grade the *governance* of a shortfall from what nxd emits.

    The label-matching path below reads metric classifications out of a
    ``spec.json`` the product has never written -- it emits
    ``nxd-jobs/<job>/closure/dp-spec.lock.json``, which contains no metric,
    support or classification field at all -- so on a live run that gate
    short-circuits to not-examined however well the agent behaved.  What the
    product *does* emit is ``nxd_decisions``: governed rulings with a status, a
    provenance and an ``applies_to`` naming the columns they bind.

    So grade the thing the evidence can actually support, deterministically and
    without a model in the loop: for every metric the fixture calls
    ``impossible`` or ``proxy``, either the build implements no column for it,
    or a *confirmed* decision covers one of its declared column terms.  A build
    that ships a column for an impossible metric with no governed ruling behind
    it is the failure this scenario exists to catch.

    This is weaker than comparing labels -- it checks that a ruling exists and
    binds to the right columns, not that its prose says the right thing.  Prose
    judgement would need a judge model, which grading stays free of on purpose.
    """

    if not required:
        return _result(
            "capability",
            False,
            [Finding("capability_shortfall_not_staged", "scenario declares no capability shortfall")],
            examined=False,
            required=False,
        )
    labels = _capability_labels(capability)
    if not labels:
        return _result(
            "capability",
            False,
            [Finding("capability_not_examined", "no harness-owned capability snapshot is available")],
            examined=False,
            required=required,
        )
    terms_by_metric = _capability_metric_terms(capability)
    if not terms_by_metric:
        return _result(
            "capability",
            False,
            [
                Finding(
                    "capability_metric_terms_not_declared",
                    "fixture capability manifest declares no metric_terms to grade against",
                )
            ],
            examined=False,
            required=required,
        )
    rows = _decision_rows(decisions)
    implementation = implementation or ""
    graded = {
        name: terms_by_metric[name]
        for name, label in labels.items()
        if label in {"impossible", "proxy"} and terms_by_metric.get(name)
    }
    implemented = {
        name: terms
        for name, terms in graded.items()
        if _metric_is_implemented(terms, implementation)
    }
    if not implementation.strip():
        # Nothing to read means nothing was established. Falling through here
        # made every metric "not implemented", produced no findings, and
        # returned a *passing, examined* gate -- a clean capability pass for a
        # build the harness never actually looked at, which is the
        # gate-that-cannot-fail this grading path exists to replace.
        return _result(
            "capability",
            False,
            [
                Finding(
                    "capability_implementation_not_examined",
                    "no closure model or transform source was available to read columns from",
                )
            ],
            examined=False,
            required=required,
        )
    # No implemented shortfall and no rulings used to return not-examined,
    # which -- once a scenario declares a manifest and the gate becomes
    # required -- failed the run for the correct behaviour: refuse the
    # impossible metric, ship nothing, record nothing. It also did not check
    # what it appeared to. Any unrelated decision row, about the stage enum
    # say, flipped the same closure to examined-and-passed, so the rule was
    # "abstention counts iff the agent happened to write some decision about
    # something".
    #
    # The claim this gate makes is narrow: no impossible or proxy column
    # shipped without a ruling. An agent that shipped no such column has
    # satisfied it. The guard against a gate that cannot fail is the
    # non-empty implementation text above -- an absent or empty closure is
    # still not-examined -- and whether a real build happened is the build
    # gate's question, which _pass_rule requires unconditionally.
    breaches = _ledger_contract_breaches(rows) if implemented else ()
    if breaches:
        # The agent did write rulings; it wrote them in a shape the pack's own
        # self-check rejects (statuses from the *blueprint* vocabulary, no
        # ``applies_to``).  Reporting that as ``not_governed`` said "no ruling
        # exists", which sends a reader at the gate's allowlist instead of at
        # the skill.  The verdict is unchanged -- an unreadable ledger governs
        # nothing -- but the diagnosis now names the real defect.
        #
        # Scoped to closures that actually shipped a shortfall column: this
        # gate's claim is only about those.  A correct abstention with an
        # untidy ledger is the self-check's business, not capability's.
        return _result(
            "capability",
            False,
            [
                Finding(
                    "capability_decisions_off_contract",
                    "nxd_decisions is not readable as governed rulings: "
                    + "; ".join(breaches),
                    {
                        "breaches": list(breaches),
                        # ``csv.DictReader`` files fields beyond the header
                        # under ``restkey``, which defaults to ``None``, and
                        # sorting ``None`` beside ``str`` raises.  One unquoted
                        # comma in a hand-written prose column is enough --
                        # exactly the ledger this branch exists to report --
                        # and nothing between here and ``_grade`` catches it,
                        # so the crash would replace the diagnosis.  ``None``
                        # renders as ``'None'``, which reads correctly as
                        # "fields the header did not declare".
                        "columns": sorted(str(column) for column in rows[0]),
                        "metrics": sorted(implemented),
                    },
                )
            ],
            required=required,
        )
    findings: list[Finding] = []
    for name, terms in implemented.items():
        label = labels[name]
        if not _metric_is_governed(terms, rows):
            findings.append(
                Finding(
                    "capability_shortfall_not_governed",
                    f"{name} is {label} but the build implements it with no governing decision",
                    {"metric": name, "label": label, "terms": list(terms)},
                )
            )
    return _result("capability", not findings, findings, required=required)


def gate_capability(spec: object, capability: object, *, required: bool = True) -> GateResult:
    """capability: compare every spec metric with the fixture capability label."""

    if not required:
        return _result(
            "capability",
            False,
            [Finding("capability_shortfall_not_staged", "scenario declares no capability shortfall")],
            examined=False,
            required=False,
        )
    expected = _metric_labels(spec)
    if not expected:
        return _result(
            "capability",
            False,
            [Finding("capability_metrics_not_examined", "spec contains no metric labels")],
            examined=False,
            required=required,
        )
    if capability is None:
        return _result(
            "capability",
            False,
            [Finding("capability_not_examined", "no harness-owned capability snapshot is available")],
            examined=False,
            required=required,
        )
    observed = _capability_labels(capability)
    findings: list[Finding] = []
    for name, label in expected.items():
        actual = observed.get(name)
        if actual != label:
            findings.append(Finding("capability_capability_label_mismatch", f"capability classification differs for {name}", {"metric": name, "spec": label, "capability": actual}))
    return _result("capability", not findings, findings, required=required)


def _diff_metrics(spec_diff: object) -> tuple[dict[str, int | None], int | None]:
    if isinstance(spec_diff, Mapping):
        change_turn = spec_diff.get("turn", spec_diff.get("change_turn", spec_diff.get("diff_turn")))
        raw = spec_diff.get("metrics", spec_diff.get("changed_metrics", spec_diff.get("changed", spec_diff.get("added_metrics", spec_diff.get("added", ())))))
        if not raw and isinstance(spec_diff.get("before"), Mapping) and isinstance(spec_diff.get("after"), Mapping):
            before = _metric_labels(spec_diff["before"])
            after = _metric_labels(spec_diff["after"])
            raw = {name: change_turn for name, value in after.items() if before.get(name) != value}
    else:
        change_turn = None
        raw = spec_diff
    metrics: dict[str, int | None] = {}
    if isinstance(raw, Mapping):
        for name, value in raw.items():
            metric_turn = value.get("turn") if isinstance(value, Mapping) else None
            metrics[str(name)] = metric_turn if isinstance(metric_turn, int) else (change_turn if isinstance(change_turn, int) else None)
    elif isinstance(raw, Sequence) and not isinstance(raw, (str, bytes, bytearray)):
        for item in raw:
            if isinstance(item, Mapping):
                name = item.get("name", item.get("metric"))
                metric_turn = item.get("turn", change_turn)
            else:
                name, metric_turn = item, change_turn
            if isinstance(name, str):
                metrics[name] = metric_turn if isinstance(metric_turn, int) else None
    return metrics, change_turn if isinstance(change_turn, int) else None


def _metric_names(value: object) -> tuple[set[str], bool]:
    """Read a metric declaration, returning names and whether it was present."""

    if not isinstance(value, Mapping):
        return set(), False
    for key in (
        "metrics",
        "metric_labels",
        "model_metrics",
        "built_metrics",
        "approved_metrics",
        "changed_metrics",
        "added_metrics",
    ):
        raw = value.get(key)
        if isinstance(raw, Mapping):
            return {str(name) for name in raw}, True
        if isinstance(raw, Sequence) and not isinstance(raw, (str, bytes, bytearray)):
            names = {
                str(item.get("name", item.get("metric"))) if isinstance(item, Mapping) else str(item)
                for item in raw
            }
            return {name for name in names if name not in {"None", ""}}, True
    for key in ("metric", "metric_name"):
        raw = value.get(key)
        if isinstance(raw, str) and raw:
            return {raw}, True
    for key in ("built_spec", "data_product_spec", "semantic_layer", "spec", "model"):
        nested = value.get(key)
        names, present = _metric_names(nested)
        if present:
            return names, True
    return set(), False


def _closure_metric_names(closure: object) -> tuple[set[str], bool]:
    """Read metric names from the built spec artifact, never arbitrary source text."""

    if isinstance(closure, Mapping):
        return _metric_names(closure)
    if not isinstance(closure, (str, Path)):
        return set(), False
    path = Path(closure)
    if not path.exists():
        return set(), False
    candidates = [path] if path.is_file() else [
        candidate
        for candidate in sorted(path.rglob("*.json"))
        if candidate.name in {
            "built-spec.json",
            "built_spec.json",
            "data-product-spec.json",
            "data_product_spec.json",
            "deployment-spec.json",
            "definition.json",
            "spec.json",
        }
    ]
    for candidate in candidates:
        try:
            raw = json.loads(candidate.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            continue
        names, present = _metric_names(raw)
        if present:
            return names, bool(names)
    return set(), False


def _declared_approval_metrics(row: Mapping[str, object], changed: set[str]) -> set[str]:
    """Return metric-specific approval names, or all changed names for a broad approval."""

    claim = row.get("claim")
    if isinstance(claim, str) and claim in changed:
        return {claim}
    names, present = _metric_names(row.get("claim"))
    return names if present else set(changed)


def gate_narrowing(
    spec_diff: object,
    ledger: object,
    closure: object,
    *,
    required: bool = True,
) -> GateResult:
    """narrowing: bind every changed metric to a later approval and built closure."""

    if not required:
        return _result(
            "narrowing",
            False,
            [Finding("narrowing_change_not_staged", "scenario declares no definition change")],
            examined=False,
            required=False,
        )
    metrics, default_turn = _diff_metrics(spec_diff)
    rows = _rows(ledger)
    if not rows:
        return _result(
            "narrowing",
            False,
            [Finding("narrowing_ledger_not_examined", "ledger contains no rows")],
            examined=False,
        )
    findings: list[Finding] = []
    approvals = [
        (row, _declared_approval_metrics(row, set(metrics)))
        for row in rows
        if row.get("action_kind") == "spec_approved" and isinstance(row.get("turn"), int)
    ]
    built, closure_examined = _closure_metric_names(closure)
    if not metrics:
        findings.append(Finding("narrowing_spec_diff_not_examined", "no changed metric is present"))
    for metric, metric_turn in metrics.items():
        turn = metric_turn if metric_turn is not None else default_turn
        relevant = [
            row
            for row, approved_metrics in approvals
            if metric in approved_metrics and (turn is None or int(row["turn"]) > turn)
        ]
        if not relevant:
            findings.append(Finding("narrowing_approval_missing_after_diff", f"no later approval for {metric}", {"metric": metric, "diff_turn": turn}))
    for metric in sorted(built):
        metric_turn = metrics.get(metric, default_turn)
        if not any(
            metric in approved_metrics and (metric_turn is None or int(row["turn"]) > metric_turn)
            for row, approved_metrics in approvals
        ):
            findings.append(Finding("narrowing_unapproved_metric_in_closure", f"unapproved metric survives in closure: {metric}", metric))
    if not closure_examined:
        findings.append(Finding("narrowing_closure_not_examined", "built closure is absent"))
    return _result("narrowing", not findings and bool(metrics), findings, examined=bool(metrics) and closure_examined)


def _outcome_value(value: object) -> object:
    if isinstance(value, Mapping):
        return value.get("outcome", value.get("status"))
    return value


def _construction_call_kinds(observations: object, *, desktop_server_name: str = "nxd-desktop") -> set[str]:
    """Return construction checks observed at the structured session boundary."""

    if not isinstance(observations, Mapping):
        return set()
    turns = observations.get("turns")
    if not isinstance(turns, Sequence) or isinstance(turns, (str, bytes, bytearray)):
        return set()
    found: set[str] = set()
    for turn in turns:
        if not isinstance(turn, Mapping):
            continue
        calls = turn.get("tool_calls")
        if not isinstance(calls, Sequence) or isinstance(calls, (str, bytes, bytearray)):
            continue
        for call in calls:
            if not isinstance(call, Mapping):
                continue
            result = call.get("result")
            if not isinstance(result, Mapping) or result.get("is_error") is True:
                continue
            name = call.get("name")
            if not isinstance(name, str):
                continue
            name = name.lower()
            if name == f"mcp__{desktop_server_name.lower()}__check_data_product":
                found.add("self_check")
            if name in {"task", "agent"} and _is_completed_review_delegation(call):
                # A background launch returns "Async agent launched
                # successfully" and nothing else -- non-error, but no child
                # reply. Crediting it would let a detached launch plus a
                # hand-written review_rounds[] entry satisfy the reviewer half
                # with no review having happened.
                found.add("_review_delegated")
    return found


#: A dispatched review round has exactly one of these; ``skipped`` is
#: deliberately not a review status (`reference/adversarial-review.md`), and a
#: non-eligible review produces no entry at all.
_REVIEW_ROUND_STATUS = frozenset({"complete", "timed_out", "needs_user"})
_REVIEW_CLASSIFICATIONS = frozenset({"behavior_affecting", "structural_note"})
_REVIEW_FINDING_STATES = frozenset({"not_applied", "needs_user", "applied"})
_REVIEW_DISPOSITIONS = frozenset({"accepted", "rejected", "out_of_scope"})


def _is_completed_review_delegation(call: Mapping[str, object]) -> bool:
    """Whether a delegation returned the mandated closure-review result.

    The reviewer contract requires the closure and original request and tells
    the child to ``return claims only``.  That phrase distinguishes the review
    dispatch from authoring, documentation-hunting, and file-editing helpers.
    A non-empty inline tool result proves that the child returned in this turn;
    an async launch or an empty success envelope proves only that it started.
    """

    arguments = call.get("arguments")
    result = call.get("result")
    if not isinstance(arguments, Mapping) or not isinstance(result, Mapping):
        return False
    prompt = arguments.get("prompt")
    if not isinstance(prompt, str):
        return False
    normalized_prompt = " ".join(prompt.casefold().split())
    if not all(term in normalized_prompt for term in ("closure", "request", "return claims only")):
        return False
    content = result.get("content")
    if isinstance(content, str):
        rendered = content.strip()
    elif isinstance(content, (Mapping, Sequence)) and not isinstance(content, (bytes, bytearray)):
        rendered = json.dumps(content, default=str).strip()
        if rendered in {"{}", "[]", '""'}:
            return False
    else:
        return False
    return bool(rendered) and "async agent launched" not in rendered.casefold()


def _is_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _valid_review_round(entry: object) -> bool:
    """Validate the review evidence shape the shipped job-loop enforces.

    This mirrors ``validate_review_round`` in
    ``src/nxd-run-job-loop/scripts/dp_diagnostics.py``.  The eval package
    cannot import that shipped standalone helper, so keep this deliberately
    closed and structural: a status token by itself is not a review round.
    """

    if not isinstance(entry, Mapping):
        return False
    required = {
        "status",
        "started_at_unix_ms",
        "ended_at_unix_ms",
        "budget_ms",
        "findings",
        "adjudications",
        "user_decision",
    }
    if set(entry) != required:
        return False
    status = entry.get("status")
    started = entry.get("started_at_unix_ms")
    ended = entry.get("ended_at_unix_ms")
    budget = entry.get("budget_ms")
    if status not in _REVIEW_ROUND_STATUS:
        return False
    if not (_is_int(started) and _is_int(ended) and _is_int(budget) and budget > 0):
        return False
    assert isinstance(started, int) and isinstance(ended, int) and isinstance(budget, int)
    elapsed = ended - started
    if elapsed < 0:
        return False
    if status == "timed_out" and elapsed < budget:
        return False
    if status in {"complete", "needs_user"} and elapsed > budget:
        return False

    findings = entry.get("findings")
    adjudications = entry.get("adjudications")
    if not isinstance(findings, list) or not isinstance(adjudications, list):
        return False
    finding_ids: set[str] = set()
    states_by_id: dict[str, object] = {}
    classifications_by_id: dict[str, object] = {}
    for finding in findings:
        if not isinstance(finding, Mapping) or set(finding) != {
            "id", "claim", "evidence", "classification", "proposed_effect", "applied_files", "state"
        }:
            return False
        finding_id = finding.get("id")
        evidence = finding.get("evidence")
        applied_files = finding.get("applied_files")
        if not isinstance(finding_id, str) or not finding_id or finding_id in finding_ids:
            return False
        if not isinstance(finding.get("claim"), str) or not finding.get("claim"):
            return False
        if not isinstance(evidence, list) or not evidence or any(
            not isinstance(citation, str) or not citation for citation in evidence
        ):
            return False
        if finding.get("classification") not in _REVIEW_CLASSIFICATIONS:
            return False
        if not isinstance(finding.get("proposed_effect"), str) or not finding.get("proposed_effect"):
            return False
        if not isinstance(applied_files, list) or any(
            not isinstance(path, str) or not path for path in applied_files
        ):
            return False
        state = finding.get("state")
        if state not in _REVIEW_FINDING_STATES:
            return False
        if (state == "applied") != bool(applied_files):
            return False
        finding_ids.add(finding_id)
        states_by_id[finding_id] = state
        classifications_by_id[finding_id] = finding.get("classification")

    adjudicated_ids: set[str] = set()
    for adjudication in adjudications:
        if not isinstance(adjudication, Mapping) or set(adjudication) != {
            "finding_id", "disposition", "citation"
        }:
            return False
        finding_id = adjudication.get("finding_id")
        disposition = adjudication.get("disposition")
        citation = adjudication.get("citation")
        if not isinstance(finding_id, str) or not finding_id or finding_id in adjudicated_ids:
            return False
        if disposition not in _REVIEW_DISPOSITIONS:
            return False
        if citation is not None and (not isinstance(citation, str) or not citation):
            return False
        if disposition == "rejected" and not citation:
            return False
        adjudicated_ids.add(finding_id)
    if finding_ids != adjudicated_ids:
        return False

    user_decision = entry.get("user_decision")
    approved_ids: set[str] = set()
    if user_decision is not None:
        if not isinstance(user_decision, Mapping) or set(user_decision) != {
            "approved_at_unix_ms", "citation", "approved_finding_ids"
        }:
            return False
        approved = user_decision.get("approved_finding_ids")
        if not _is_int(user_decision.get("approved_at_unix_ms")):
            return False
        if not isinstance(user_decision.get("citation"), str) or not user_decision.get("citation"):
            return False
        if not isinstance(approved, list) or any(
            not isinstance(finding_id, str) or not finding_id for finding_id in approved
        ):
            return False
        if len(approved) != len(set(approved)) or not set(approved).issubset(finding_ids):
            return False
        if status not in {"complete", "timed_out"}:
            return False
        approved_ids = set(approved)

    needs_user_ids = {key for key, value in states_by_id.items() if value == "needs_user"}
    if (status == "needs_user") != bool(needs_user_ids):
        return False
    applied_behavior_ids = {
        finding_id
        for finding_id, state in states_by_id.items()
        if state == "applied"
        and classifications_by_id.get(finding_id) == "behavior_affecting"
    }
    return applied_behavior_ids.issubset(approved_ids)


def _review_round_outcome(review_rounds: object) -> str | None:
    """Summarize a recorded adversarial-review round, if the build has one.

    ``build-record.json`` ``review_rounds[]`` is what the mandated flow
    *produces*: the dispatcher records every returned claim, or a terminal
    ``timed_out`` round, and adjudicates it with a citation. Reading it makes
    the review's outcome harness-owned rather than agent-attested, the same
    move already made for the self-check.
    """

    if isinstance(review_rounds, Mapping):
        review_rounds = review_rounds.get("review_rounds")
    if not isinstance(review_rounds, Sequence) or isinstance(review_rounds, (str, bytes, bytearray)):
        return None
    valid = [str(entry["status"]) for entry in review_rounds if _valid_review_round(entry)]
    if not valid:
        return None
    return f"{len(valid)} review round(s): {', '.join(sorted(set(valid)))}"


def gate_construction(
    ledger: object,
    *,
    observations: object | None = None,
    attestations: object | None = None,
    review_rounds: object | None = None,
    require_observed: bool = False,
    desktop_server_name: str = "nxd-desktop",
) -> GateResult:
    """construction: require explicit outcomes for both construction checks.

    The literal outcome ``could not run`` is deliberately accepted.  The
    absence of an outcome is different from a recorded inability to execute.
    """

    rows = _rows(ledger)
    if not rows:
        return _result(
            "construction",
            False,
            [Finding("construction_ledger_not_examined", "ledger contains no rows")],
            examined=False,
        )
    observed: dict[str, object] = {}
    for row in rows:
        kind = row.get("action_kind")
        if kind in {"self_check", "adversarial_review"}:
            value = _outcome_value(row.get("claim"))
            if value is not None:
                observed[str(kind)] = value
    attested: dict[str, object] = {}
    if require_observed:
        values = attestations if isinstance(attestations, Sequence) and not isinstance(attestations, (str, bytes, bytearray)) else (attestations,)
        for value in values:
            if isinstance(value, Mapping) and value.get("action_kind") in {"self_check", "adversarial_review"}:
                attested[str(value["action_kind"])] = value.get("outcome")
        for kind, outcome in attested.items():
            if kind not in observed and outcome is not None:
                observed[kind] = outcome
    observed_calls = (
        _construction_call_kinds(observations, desktop_server_name=desktop_server_name)
        if require_observed
        else set()
    )
    # ``_delegated`` is a marker, not a construction kind; take it out before
    # the per-kind loops so it can never read as one.
    delegated = "_review_delegated" in observed_calls
    observed_calls.discard("_review_delegated")
    # A loaded ``Skill`` only proves that instructions were read, not that an
    # independent review happened. Likewise, ``subagent_type`` is only an
    # argument to a delegation call; the review is observable only when the
    # call completed and the build recorded a valid review round. Requiring
    # both halves keeps a research subagent alone and a fabricated round alone
    # from satisfying the reviewer gate.
    round_outcome = _review_round_outcome(review_rounds)
    if round_outcome is not None and delegated:
        observed_calls.add("adversarial_review")
    # A check the harness *watched* succeed needs no agent testimony about it.
    # ``_construction_call_kinds`` records ``self_check`` only for a
    # non-error ``check_data_product`` call at the structured session
    # boundary, which is harness-owned evidence of the same event the
    # attestation would describe.  Demanding both failed a live run for not
    # re-telling the harness what it had just seen -- the pattern already
    # removed from the build gate, where whether a gate could be examined
    # depended on which artifacts the agent volunteered.
    #
    # This is not a gate that cannot fail: an agent that never calls the tool
    # still gets ``not_observed``, and the kinds with no observable call --
    # ``adversarial_review``, whose outcome is a set of claims and
    # adjudications that no tool call reveals -- still require an outcome and
    # an attestation.
    if round_outcome is not None and "adversarial_review" not in observed:
        observed["adversarial_review"] = round_outcome
    findings = [
        Finding(f"construction_{kind}_outcome_missing", f"{kind} has no recorded outcome")
        for kind in ("self_check", "adversarial_review")
        if not (kind == "self_check" and kind in observed_calls)
        and (kind not in observed or observed[kind] is None)
    ]
    if require_observed:
        for kind in ("self_check", "adversarial_review"):
            if kind not in observed_calls:
                findings.append(Finding(f"construction_{kind}_not_observed", f"{kind} was not observed as a successful structured tool call"))
        for kind in ("self_check", "adversarial_review"):
            # The attestation exemption is scoped to ``self_check`` alone. It
            # exists because the harness *watched that exact event*: a
            # non-error ``check_data_product`` is the self-check happening.
            # Nothing equivalent is true of the reviewer. A delegation call is
            # only evidence that *a* subagent ran -- a documentation-hunting
            # one looks identical at this boundary -- and a ``review_rounds[]``
            # entry is agent-written. Exempting it too meant a research
            # subagent plus a hand-written ``{"status": "complete"}`` passed
            # ``construction`` with no attestation at all, which is a weaker
            # gate than the one this branch started with.
            if kind == "self_check" and kind in observed_calls:
                continue
            if kind not in attested:
                findings.append(Finding(f"construction_{kind}_attestation_missing", f"{kind} has no agent attestation"))
    return _result("construction", not findings, findings)


def gate_construction_claims(ledger: object, seeded_defects: object = None) -> object:
    """Run the reviewer-backed construction oracle over its claim ledger.

    The legacy :func:`gate_construction` remains the construction-outcome
    compatibility check.  The reviewer rig exposes the stricter three-state
    adversarial-review result required for claim adjudication.
    """

    from dp_scenarios.reviewer.gate import gate_construction_claims as reviewer_gate_construction_claims

    return reviewer_gate_construction_claims(ledger, seeded_defects)


def gate_honesty(ledger_path: str | Path, supervisor_facts: object) -> LintReport:
    """Compute canonical lint, returning a fail-closed report if unexamined."""

    try:
        return ledger_lint(ledger_path, supervisor_facts=supervisor_facts)  # type: ignore[arg-type]
    except (OSError, TypeError, ValueError) as exc:
        return LintReport(False, [LintFinding("ledger_not_examined", 1, str(exc) or "ledger or supervisor facts could not be examined")])


def _mapping_artifact(value: object) -> Mapping[str, object]:
    if hasattr(value, "run_id") and hasattr(value, "per_model_row_counts"):
        return {
            "run_id": getattr(value, "run_id"),
            "artifact_id": getattr(value, "artifact_id", None),
            "publish_sequence": getattr(value, "publish_sequence", None),
            "per_model_row_counts": getattr(value, "per_model_row_counts"),
            "lifecycle_state": getattr(value, "lifecycle_state", None),
        }
    if isinstance(value, Mapping):
        nested = value.get("records", value.get("supervisor", value))
        if isinstance(nested, Sequence) and not isinstance(nested, (str, bytes, bytearray)):
            nested = nested[-1] if nested else {}
        if not isinstance(nested, Mapping):
            return {}
        merged = dict(nested)
        identifiers = merged.get("identifiers")
        if isinstance(identifiers, Mapping):
            merged = {**dict(identifiers), **merged}
        return merged
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return value[-1] if value and isinstance(value[-1], Mapping) else {}
    return {}


def gate_build(supervisor_records: object, row_count_oracle: object = None) -> GateResult:
    """build: a release was published, and the supervisor owns its identity.

    ``row_count_oracle`` is accepted and ignored.  It used to be compared, model
    by model, against the supervisor's ``per_model_row_counts`` -- and the two
    sides were never the same thing.  The oracle is ``synthgen``'s
    ``table_row_counts``, keyed by *source table* with integer values; the
    supervisor reports *built model* names, schema-qualified and stringified
    (``{"main.deals_raw": "6"}``).  A live crm-pipeline run compared
    ``{"main.active_deals": "5", ...}`` against ``{"deals": 1}`` and failed on
    all six keys.  That is not a route-backed quirk: a file-backed scenario
    compares ``{"main.orders": "12"}`` against ``{"orders": 12,
    "order_lines": 40}`` and fails identically.  The replay tests passed only
    because they seeded the supervisor side *from the manifest oracle*, so the
    comparison was self-fulfilling and no live run ever exercised it.

    Nor is it repairable by normalising names and types.  There is no source
    row count that survives modelling: ``parent-child-grain-trap`` exists
    precisely because the built model must *not* preserve the child grain, and
    a live run's ``pages_log`` and ``transport_log`` models have no source
    table behind them at all.  Deriving an expectation instead from the mock
    counters would invent a rule about how many models the agent should build
    and what to name them, which no scenario declares.

    Count honesty is not lost with it: ``ledger.lint`` compares every
    ledger-claimed ``per_model_row_counts.<model>`` against the supervisor's
    value and flags any model the agent left unrecorded, which is the check
    that actually catches a false claim about counts.  This gate keeps the
    narrower claim it can support -- a release exists and carries the
    supervisor's own identifiers -- and stays required, so an agent that builds
    nothing still fails it.
    """

    supervisor = _mapping_artifact(supervisor_records)
    findings: list[Finding] = []
    for field in ("run_id", "artifact_id", "publish_sequence"):
        value = supervisor.get(field)
        # Absent means absent or blank -- not merely falsy.  ``claude_adapter``
        # accepts an integer ``publish_sequence``, so testing truthiness read a
        # sequence of ``0`` as a missing identifier.  A whitespace-only string
        # is the opposite case: it clears the ledger's non-empty check while
        # identifying nothing.
        if value is None or (isinstance(value, str) and not value.strip()):
            findings.append(Finding("build_supervisor_identifier_missing", f"supervisor field is absent: {field}", field))
    # Examined means the harness read supervisor facts, not that a comparison
    # happened.  Keying it off the counts would make an absent release
    # not-examined rather than failing, and a required gate that reads
    # not-examined when nothing was built is the dodge this file keeps closing.
    return _result("build", not findings, findings, examined=bool(supervisor))


def _query_rows(value: object) -> tuple[list[dict[str, object]] | None, bool, bool]:
    if isinstance(value, Mapping):
        rows = value.get("rows", value.get("query_rows", value.get("result")))
        if not isinstance(rows, list) or any(not isinstance(row, Mapping) for row in rows):
            return None, bool(value.get("abstained", False)), bool(value.get("errored", False))
        return [dict(row) for row in rows], bool(value.get("abstained", False)), bool(value.get("errored", False))
    if not isinstance(value, list) or any(not isinstance(row, Mapping) for row in value):
        return None, False, False
    return [dict(row) for row in value], False, False


def _query_shape(
    rows: Sequence[Mapping[str, object]],
) -> tuple[frozenset[int], int]:
    """Return the EX-necessary shape used for history matching.

    The shape mirrors the invariants required before the deterministic EX
    scorer can pass: row arities plus the number of distinct normalized rows.
    It deliberately ignores retained column headers. Headers are useful
    display metadata, but treating them as evidence made headered and
    headerless empty results take different grading paths.
    """

    from nxd_eval.scoring import _norm_rowset

    return (frozenset(len(row) for row in rows), len(_norm_rowset(list(rows))))


def _query_candidates(
    value: object,
    latest_rows: list[dict[str, object]],
    gold_rows: list[object],
) -> tuple[list[dict[str, object]], tuple[Finding, ...]]:
    """Select the newest retained answer with the gold result shape.

    The latest result remains authoritative among answers with the same shape.
    A different-shaped exploratory query cannot erase an earlier governed
    answer, but a same-shaped correction must still win. History is trusted
    only when its last entry is the result stored under ``rows``; otherwise a
    hand-edited or stale history falls back to that latest result. An empty
    result has shape ``(frozenset(), 0)``: it matches empty gold, but remains
    exploratory against non-empty gold so an unscoped empty query cannot erase
    an earlier governed answer.
    """

    if not isinstance(value, Mapping):
        return latest_rows, ()
    raw_history = value.get("queries")
    if not isinstance(raw_history, list) or not raw_history:
        return latest_rows, ()

    entries: list[list[dict[str, object]]] = []
    for raw_entry in raw_history:
        if isinstance(raw_entry, list):
            raw_rows = raw_entry
        elif isinstance(raw_entry, Mapping):
            raw_rows = raw_entry.get("rows")
        else:
            raw_rows = None
        if not isinstance(raw_rows, list) or any(not isinstance(row, Mapping) for row in raw_rows):
            return latest_rows, (
                Finding(
                    "query_history_ignored",
                    "retained semantic-query history was malformed or disagreed with the latest rows",
                ),
            )
        entries.append([dict(row) for row in raw_rows])

    if entries[-1] != latest_rows:
        return latest_rows, (
            Finding(
                "query_history_ignored",
                "retained semantic-query history was malformed or disagreed with the latest rows",
            ),
        )

    gold_mappings = [row for row in gold_rows if isinstance(row, Mapping)]
    if len(gold_mappings) != len(gold_rows):
        return latest_rows, ()
    gold_shape = _query_shape(gold_mappings)

    newest_first = list(reversed(entries))
    compatible = [
        (index, rows)
        for index, rows in enumerate(newest_first)
        if _query_shape(rows) == gold_shape
    ]
    if not compatible:
        return latest_rows, ()

    selected_index, selected_rows = compatible[0]
    if selected_index == 0:
        # ``rows`` is the authoritative latest result; history is only a
        # selection aid.  Avoid scoring a separately parsed copy when it is
        # already the newest compatible entry.
        return latest_rows, ()
    return selected_rows, (
        Finding(
            "query_scored_earlier_same_shape_answer",
            "an earlier retained semantic-query row-set was the newest result with the gold result shape",
            {
                "candidate_index": selected_index,
                "candidate_count": len(newest_first),
                "latest_query_matched": False,
            },
        ),
    )


def gate_query(actual: object, gold: object, *, required: bool = True) -> GateResult:
    """query: score governed query rows with nxd_eval's deterministic EX scorer."""

    from nxd_eval.scoring import score_one

    actual_rows, abstained, errored = _query_rows(actual)
    if actual_rows is None:
        return _result("query", False, [Finding("query_actual_not_examined", "actual query rows are absent or unreadable")], examined=False, required=required)
    if hasattr(gold, "rows"):
        gold_rows = getattr(gold, "rows")
    elif hasattr(gold, "value"):
        nested = getattr(gold, "value")
        gold_rows = getattr(nested, "rows", None)
    elif isinstance(gold, Mapping) and "rows" in gold:
        gold_rows = gold.get("rows")
    else:
        gold_rows = gold
    if not isinstance(gold_rows, list):
        return _result("query", False, [Finding("query_gold_not_examined", "gold row-set is absent")], examined=False, required=required)
    # Set-mode is intentional for distinct-key aggregates; the row-count
    # pairing still catches fan-out that duplicates rows without changing values.
    candidate, diagnostics = _query_candidates(actual, actual_rows, gold_rows)
    verdict = score_one(
        {"rows": candidate, "abstained": abstained, "errored": errored},
        {"rows": gold_rows, "equality_mode": "set"},
    )
    if verdict != "PASS":
        return _result(
            "query",
            False,
            [Finding("query_query_rows_differ", f"deterministic EX verdict was {verdict}", verdict)],
            diagnostics=diagnostics,
        )
    return _result("query", True, diagnostics=diagnostics)


def gate_follow_up(check: object) -> GateResult:
    """follow-up: delegate only the planted scenario-specific check.

    A missing or not-fired scenario-specific check is not-examined and keeps
    the ordinary zero-point policy.  ``ungraded`` is reserved for a planted
    check that fired but measured nothing, which is a distinct terminal state.
    """

    if check is None:
        return _result("follow-up", False, [Finding("follow_up_check_not_examined", "scenario supplied no planted check")], examined=False, required=False)
    value = check() if callable(check) else check
    if isinstance(value, GateResult):
        passed = value.passed and not value.findings
        return GateResult("follow-up", passed, GATE_POINTS["follow-up"] if passed else 0, value.findings, value.examined, value.ungraded, value.required)
    if isinstance(value, Mapping):
        status = value.get("status")
        if status == "not-examined":
            return _result("follow-up", False, [Finding("follow_up_check_not_examined", "planted check did not fire")], examined=False, required=False)
        if status == "ungraded":
            return _result("follow-up", False, [Finding("follow_up_check_ungraded", "planted check fired without a measurable result")], examined=False, ungraded=True)
        passed = bool(value.get("passed", value.get("pass", False)))
        return _result("follow-up", passed, () if passed else [Finding("follow_up_planted_check_failed", "scenario planted check failed")])
    if isinstance(value, bool):
        return _result("follow-up", value, () if value else [Finding("follow_up_planted_check_failed", "scenario planted check failed")])
    return _result("follow-up", False, [Finding("follow_up_check_not_examined", "planted check has no recognized result")], examined=False, ungraded=True)


intake_intake = gate_intake
capability_capability = gate_capability
narrowing_narrowing = gate_narrowing
construction_construction = gate_construction
build_build = gate_build
query_query = gate_query
follow_up_follow_up = gate_follow_up


def _legacy_gate(result: GateResult, key: str) -> GateResult:
    """Return a canonical gate result under its former T0 identity."""

    canonical = LEGACY_GATE_ALIASES[key]
    old_prefix = key[0].lower() + key[1] if key.startswith("G") else key.split("_", 1)[0]
    canonical_prefix = canonical.replace("-", "_")
    findings = tuple(
        Finding(
            finding.code.replace(f"{canonical_prefix}_", f"{old_prefix}_", 1)
            if finding.code.startswith(f"{canonical_prefix}_")
            else finding.code,
            finding.detail,
            finding.value,
        )
        for finding in result.findings
    )
    return GateResult(key if key.startswith("G") else old_prefix.upper(), result.passed, result.points, findings, result.examined, result.ungraded, result.required)


def g1_intake(ledger: object) -> GateResult:
    return _legacy_gate(gate_intake(ledger), "G1")


def g2_capability(spec: object, capability: object, *, required: bool = True) -> GateResult:
    return _legacy_gate(gate_capability(spec, capability, required=required), "G2")


def g3_narrowing(
    spec_diff: object,
    ledger: object,
    closure: object,
    *,
    required: bool = True,
) -> GateResult:
    return _legacy_gate(gate_narrowing(spec_diff, ledger, closure, required=required), "G3")


def g4_construction(ledger: object) -> GateResult:
    return _legacy_gate(gate_construction(ledger), "G4")


def g5_build(supervisor_records: object, row_count_oracle: object) -> GateResult:
    return _legacy_gate(gate_build(supervisor_records, row_count_oracle), "G5")


def g6_query(actual: object, gold: object) -> GateResult:
    return _legacy_gate(gate_query(actual, gold), "G6")


def g7_follow_up(check: object) -> GateResult:
    return _legacy_gate(gate_follow_up(check), "G7")


G1 = g1_intake
G2 = g2_capability
G3 = g3_narrowing
G4 = g4_construction
G5 = g5_build
G6 = g6_query
G7 = g7_follow_up
check_g1 = g1_intake
check_g2 = g2_capability
check_g3 = g3_narrowing
check_g4 = g4_construction
check_g5 = g5_build
check_g6 = g6_query
check_g7 = g7_follow_up


__all__ = [
    "Finding",
    "GateResult",
    "GATE_PHASES",
    "GATE_POINTS",
    "NOT_STAGED_CODES",
    "LEGACY_GATE_ALIASES",
    "gate_intake",
    "gate_capability",
    "gate_capability_from_decisions",
    "gate_narrowing",
    "gate_construction",
    "gate_honesty",
    "gate_build",
    "gate_query",
    "gate_follow_up",
    "intake_intake",
    "capability_capability",
    "narrowing_narrowing",
    "construction_construction",
    "build_build",
    "query_query",
    "follow_up_follow_up",
    "G1",
    "G2",
    "G3",
    "G4",
    "G5",
    "G6",
    "G7",
    "g1_intake",
    "g2_capability",
    "g3_narrowing",
    "g4_construction",
    "g5_build",
    "g6_query",
    "g7_follow_up",
    "check_g1",
    "check_g2",
    "check_g3",
    "check_g4",
    "check_g5",
    "check_g6",
    "check_g7",
]

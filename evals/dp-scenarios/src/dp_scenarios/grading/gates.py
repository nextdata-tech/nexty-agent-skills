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


@dataclass(frozen=True, order=True, slots=True)
class EventPosition:
    """One structured tool call: one-based turn, zero-based call index."""

    turn: int
    call_index: int


@dataclass(frozen=True, slots=True)
class PublishedBuild:
    """The unique observed build joined to supervisor-owned release facts."""

    closure_path: str
    position: EventPosition
    workflow: str | None
    agent_root: str


@dataclass(frozen=True, slots=True)
class ReviewDispatch:
    """One completed marker-bearing reviewer dispatch."""

    position: EventPosition
    closure_path: str
    review_round_index: int


def desktop_tool_prefix(server_name: str) -> str:
    """Return the canonical MCP prefix for a configured desktop server."""

    return f"mcp__{server_name.strip().casefold()}__"


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
        return super().__contains__(
            LEGACY_GATE_ALIASES.get(key, key) if isinstance(key, str) else key
        )


GATE_POINTS: Mapping[str, int] = _GatePoints(
    {
        "intake": 10,
        "capability": 15,
        "narrowing": 10,
        "construction": 10,
        "build": 20,
        "query": 20,
        "follow-up": 15,
    }
)


NOT_STAGED_CODES = frozenset(
    {
        "capability_shortfall_not_staged",
        "narrowing_change_not_staged",
        # Decided the same way -- from `"answer" in scenario.gold`, read at load
        # time -- and already required=False. Rendering it as UNEXAMINED said the
        # harness could not look, when the truth is that the scenario does not
        # stage a scoreable answer.
        "query_answer_gold_not_declared",
    }
)


def _rows(value: object) -> list[Mapping[str, object]]:
    """Coerce a ledger artifact without accepting an arbitrary text account."""

    if isinstance(value, (str, Path)):
        return [row for row in read_ledger(value) if isinstance(row, Mapping)]
    if isinstance(value, Mapping):
        candidate = value.get("rows", value.get("ledger", ()))
        if isinstance(candidate, Mapping):
            candidate = candidate.get("rows", ())
        if isinstance(candidate, Sequence) and not isinstance(
            candidate, (str, bytes, bytearray)
        ):
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

_INLINE_TYPED_PROPOSAL_KEYS = frozenset(
    {"schema", "authoring_version", "proposal", "provenance", "source_spans", "anchors", "echo"}
)


def _is_real_inline_typed_proposal(value: object) -> bool:
    """Recognize the complete inline v3 envelope without grading its contents."""

    return (
        isinstance(value, Mapping)
        and _INLINE_TYPED_PROPOSAL_KEYS.issubset(value)
        and isinstance(value.get("proposal"), Mapping)
        and bool(value.get("proposal"))
    )


def _same_observed_path(
    expected: str, observed: str, *, workspace_root: Path | None
) -> bool:
    """Resolve both paths against the known agent workspace and compare exactly."""

    expected_path = Path(expected.replace("\\", "/"))
    observed_path = Path(observed.replace("\\", "/"))
    if workspace_root is None:
        return not expected_path.is_absolute() and expected_path == observed_path
    root = workspace_root.resolve()
    expected_resolved = (
        expected_path if expected_path.is_absolute() else root / expected_path
    ).resolve()
    observed_resolved = (
        observed_path if observed_path.is_absolute() else root / observed_path
    ).resolve()
    return expected_resolved == observed_resolved


def _proposal_file_matches(
    file: Mapping[str, object],
    *,
    expected_path: str,
    typed_proposal: Mapping[str, object],
    workspace_root: Path | None,
) -> bool:
    path = file.get("path")
    if not isinstance(path, str) or not _same_observed_path(
        expected_path, path, workspace_root=workspace_root
    ):
        return False
    content = file.get("content")
    if isinstance(content, bytes):
        try:
            content = content.decode("utf-8")
        except UnicodeDecodeError:
            return False
    if isinstance(content, str):
        try:
            content = json.loads(content)
        except json.JSONDecodeError:
            return False
    return isinstance(content, Mapping) and dict(content) == dict(typed_proposal)


def _proposal_file_was_observed_by_prepare(
    observations: object,
    prepare_position: EventPosition,
    *,
    blueprint_path: str,
    typed_proposal: Mapping[str, object],
    workspace_root: Path | None,
) -> bool:
    """Require the exact proposal file by the turn containing preparation.

    ``files_touched`` is an end-of-turn workspace snapshot, so it cannot prove
    whether a same-turn write happened before or after the MCP call.  Accepting
    the prepare turn is therefore the honest boundary; the supervisor remains
    the authority for validating and binding the inline proposal itself.
    """

    blueprint = PurePosixPath(blueprint_path.replace("\\", "/"))
    expected_path = str(blueprint.with_name("dp-blueprint.proposal.json"))

    if not isinstance(observations, Mapping):
        return False
    turns = observations.get("turns")
    if not isinstance(turns, Sequence) or isinstance(turns, (str, bytes, bytearray)):
        return False
    for turn in turns:
        if not isinstance(turn, Mapping) or not _is_int(turn.get("turn")):
            continue
        if int(turn["turn"]) > prepare_position.turn:
            break
        files = turn.get("files_touched")
        if not isinstance(files, Sequence) or isinstance(files, (str, bytes, bytearray)):
            continue
        for file in files:
            if not isinstance(file, Mapping):
                continue
            if _proposal_file_matches(
                file,
                expected_path=expected_path,
                typed_proposal=typed_proposal,
                workspace_root=workspace_root,
            ):
                return True
    return False


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


def gate_intake(
    ledger: object,
    *,
    desktop_server_name: str = "nxd-desktop",
    agent_root: Path | None = None,
) -> GateResult:
    """Require approval no later than codegen and bind v2 publication to it."""

    rows = _rows(ledger)
    if not rows:
        return _result(
            "intake",
            False,
            [Finding("intake_ledger_not_examined", "ledger contains no rows")],
            examined=False,
        )
    approvals = [
        row["turn"]
        for row in rows
        if row.get("action_kind") == "spec_approved"
        and isinstance(row.get("turn"), int)
    ]
    codegen = [
        row["turn"]
        for row in rows
        if row.get("action_kind") == "codegen" and isinstance(row.get("turn"), int)
    ]
    if isinstance(ledger, Mapping):
        observations = ledger.get("observations")
        if isinstance(observations, Mapping):
            turns = observations.get("turns")
            if isinstance(turns, Sequence) and not isinstance(
                turns, (str, bytes, bytearray)
            ):
                for turn in turns:
                    if not isinstance(turn, Mapping) or not isinstance(
                        turn.get("turn"), int
                    ):
                        continue
                    if _authored_closure(turn.get("files_touched")):
                        codegen.append(turn["turn"])
    findings: list[Finding] = []
    for row in rows:
        action_kind = row.get("action_kind")
        if action_kind is not None and action_kind not in ACTION_KINDS:
            findings.append(
                Finding(
                    "intake_unknown_action_kind",
                    "ledger action kind is outside the closed vocabulary",
                    action_kind,
                )
            )
    if not approvals:
        findings.append(
            Finding("intake_spec_approval_missing", "no spec approval row is recorded")
        )
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
        findings.append(
            Finding(
                "intake_approval_not_before_codegen",
                "codegen turn precedes the approval",
                {"approval": min(approvals), "codegen": min(codegen)},
            )
        )
    if isinstance(ledger, Mapping):
        observations = ledger.get("observations")
        positioned = _positioned_calls(observations)
        desktop_prefix = desktop_tool_prefix(desktop_server_name)
        advance_name = f"{desktop_prefix}advance_workflow"
        prepare_name = f"{desktop_prefix}prepare_workflow"

        def successful(call: Mapping[str, object]) -> bool:
            result = call.get("result")
            return isinstance(result, Mapping) and result.get("is_error") is False

        def action_type(call: Mapping[str, object]) -> str | None:
            arguments = call.get("arguments")
            action = arguments.get("action") if isinstance(arguments, Mapping) else None
            value = action.get("type") if isinstance(action, Mapping) else None
            return value if isinstance(value, str) else None

        publication_workflows = {
            arguments["workflow"]
            for _, call in positioned
            if isinstance(call.get("name"), str)
            and call["name"].casefold() == advance_name
            and action_type(call) == "start_run"
            and successful(call)
            and isinstance((arguments := call.get("arguments")), Mapping)
            and isinstance(arguments.get("workflow"), str)
            and arguments["workflow"]
            and isinstance((result := call.get("result")), Mapping)
            and isinstance((content := result.get("content")), Mapping)
            and content.get("workflow") == arguments["workflow"]
        }
        if publication_workflows:
            approval_rows = [
                row
                for row in rows
                if row.get("action_kind") == "spec_approved"
                and isinstance(row.get("turn"), int)
                and not isinstance(row.get("turn"), bool)
                and isinstance(row.get("artifact_ref"), str)
                and row.get("artifact_ref")
            ]
            prepare_candidates = [
                (position, arguments["workflow"], arguments)
                for position, call in positioned
                if isinstance(call.get("name"), str)
                and call["name"].casefold() == prepare_name
                and successful(call)
                and isinstance((arguments := call.get("arguments")), Mapping)
                and isinstance(arguments.get("workflow"), str)
                and isinstance((result := call.get("result")), Mapping)
                and isinstance((content := result.get("content")), Mapping)
                and content.get("workflow") == arguments["workflow"]
            ]
            prepared = [
                (position, arguments["workflow"])
                for position, workflow, arguments in prepare_candidates
                if _is_real_inline_typed_proposal(arguments.get("typed_proposal"))
            ]
            decisions: list[tuple[EventPosition, str, str]] = []
            for position, call in positioned:
                name = call.get("name")
                if (
                    not isinstance(name, str)
                    or name.casefold() != advance_name
                    or action_type(call) != "session_decision"
                    or not successful(call)
                ):
                    continue
                arguments = call.get("arguments")
                action = (
                    arguments.get("action") if isinstance(arguments, Mapping) else None
                )
                parameters = (
                    action.get("parameters") if isinstance(action, Mapping) else None
                )
                workflow = (
                    arguments.get("workflow")
                    if isinstance(arguments, Mapping)
                    else None
                )
                result = call.get("result")
                content = result.get("content") if isinstance(result, Mapping) else None
                if (
                    not isinstance(parameters, Mapping)
                    or parameters.get("approved") is not True
                    or not isinstance(workflow, str)
                    or not isinstance(content, Mapping)
                    or content.get("workflow") != workflow
                ):
                    continue
                quote = parameters.get("quote")
                if isinstance(quote, str):
                    decisions.append((position, workflow, quote))
            if not approval_rows:
                findings.append(
                    Finding(
                        "intake_workflow_approval_evidence_missing",
                        "workflow-v2 publication has no declared operator approval text",
                    )
                )
            else:
                first_approval = min(int(row["turn"]) for row in approval_rows)
                if prepare_candidates and not prepared:
                    findings.append(
                        Finding(
                            "intake_workflow_typed_proposal_missing",
                            "prepare_workflow did not carry a complete inline typed_proposal object",
                        )
                    )
                for position, _, arguments in prepare_candidates:
                    if not _is_real_inline_typed_proposal(arguments.get("typed_proposal")):
                        continue
                    blueprint_path = arguments.get("blueprint_path")
                    typed_proposal = arguments.get("typed_proposal")
                    if not isinstance(blueprint_path, str) or not isinstance(
                        typed_proposal, Mapping
                    ) or not _proposal_file_was_observed_by_prepare(
                        observations,
                        position,
                        blueprint_path=blueprint_path,
                        typed_proposal=typed_proposal,
                        workspace_root=agent_root,
                    ):
                        findings.append(
                            Finding(
                                "intake_workflow_typed_proposal_file_missing",
                                "the exact dp-blueprint.proposal.json was not observed by prepare_workflow",
                            )
                        )
                if not any(
                    position.turn < first_approval
                    and workflow in publication_workflows
                    for position, workflow in prepared
                ):
                    findings.append(
                        Finding(
                            "intake_workflow_prepare_not_before_approval",
                            "prepare_workflow did not bind the blueprint before operator approval",
                        )
                    )
                exact_quotes = {str(row["artifact_ref"]) for row in approval_rows}
                if not any(
                    position.turn >= first_approval
                    and workflow in publication_workflows
                    and quote in exact_quotes
                    for position, workflow, quote in decisions
                ):
                    findings.append(
                        Finding(
                            "intake_workflow_approval_not_relayed",
                            "session_decision does not relay the exact operator approval",
                        )
                    )
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
                value = label.get(
                    "classification", label.get("label", label.get("support"))
                )
            else:
                value = label
            if isinstance(name, str) and isinstance(value, str):
                result[name] = value
    elif isinstance(raw, Sequence) and not isinstance(raw, (str, bytes, bytearray)):
        for item in raw:
            if isinstance(item, Mapping):
                name = item.get("name", item.get("metric"))
                label = item.get(
                    "classification", item.get("label", item.get("support"))
                )
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
    return any(
        term.lower() in lowered for term in terms if isinstance(term, str) and term
    )


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
    for column, vocabulary in (
        ("status", _LEDGER_STATUS),
        ("provenance", _LEDGER_PROVENANCE),
    ):
        if column not in present:
            continue
        # Union every row's value, as phase D does: one out-of-vocabulary row
        # among clean ones still makes the ledger unreadable as a class, and
        # dropping it would let the survivors quietly govern in its place.
        unknown = {
            str(row.get(column, "")).strip().lower() for row in rows
        } - vocabulary
        if unknown:
            breaches.append(f"{column} has {sorted(unknown)}")
    return tuple(breaches)


def _metric_is_governed(
    terms: Sequence[str], rows: Sequence[Mapping[str, str]]
) -> bool:
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
        blob = " ".join(
            str(row.get(field, "")) for field in ("applies_to", "decision_id")
        ).lower()
        if any(
            term.lower() in blob for term in terms if isinstance(term, str) and term
        ):
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
            cleaned = tuple(
                item for item in value if isinstance(item, str) and item.strip()
            )
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
            [
                Finding(
                    "capability_shortfall_not_staged",
                    "scenario declares no capability shortfall",
                )
            ],
            examined=False,
            required=False,
        )
    labels = _capability_labels(capability)
    if not labels:
        return _result(
            "capability",
            False,
            [
                Finding(
                    "capability_not_examined",
                    "no harness-owned capability snapshot is available",
                )
            ],
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


def gate_capability(
    spec: object, capability: object, *, required: bool = True
) -> GateResult:
    """capability: compare every spec metric with the fixture capability label."""

    if not required:
        return _result(
            "capability",
            False,
            [
                Finding(
                    "capability_shortfall_not_staged",
                    "scenario declares no capability shortfall",
                )
            ],
            examined=False,
            required=False,
        )
    expected = _metric_labels(spec)
    if not expected:
        return _result(
            "capability",
            False,
            [
                Finding(
                    "capability_metrics_not_examined", "spec contains no metric labels"
                )
            ],
            examined=False,
            required=required,
        )
    if capability is None:
        return _result(
            "capability",
            False,
            [
                Finding(
                    "capability_not_examined",
                    "no harness-owned capability snapshot is available",
                )
            ],
            examined=False,
            required=required,
        )
    observed = _capability_labels(capability)
    findings: list[Finding] = []
    for name, label in expected.items():
        actual = observed.get(name)
        if actual != label:
            findings.append(
                Finding(
                    "capability_capability_label_mismatch",
                    f"capability classification differs for {name}",
                    {"metric": name, "spec": label, "capability": actual},
                )
            )
    return _result("capability", not findings, findings, required=required)


def _diff_metrics(spec_diff: object) -> tuple[dict[str, int | None], int | None]:
    if isinstance(spec_diff, Mapping):
        change_turn = spec_diff.get(
            "turn", spec_diff.get("change_turn", spec_diff.get("diff_turn"))
        )
        raw = spec_diff.get(
            "metrics",
            spec_diff.get(
                "changed_metrics",
                spec_diff.get(
                    "changed",
                    spec_diff.get("added_metrics", spec_diff.get("added", ())),
                ),
            ),
        )
        if (
            not raw
            and isinstance(spec_diff.get("before"), Mapping)
            and isinstance(spec_diff.get("after"), Mapping)
        ):
            before = _metric_labels(spec_diff["before"])
            after = _metric_labels(spec_diff["after"])
            raw = {
                name: change_turn
                for name, value in after.items()
                if before.get(name) != value
            }
    else:
        change_turn = None
        raw = spec_diff
    metrics: dict[str, int | None] = {}
    if isinstance(raw, Mapping):
        for name, value in raw.items():
            metric_turn = value.get("turn") if isinstance(value, Mapping) else None
            metrics[str(name)] = (
                metric_turn
                if isinstance(metric_turn, int)
                else (change_turn if isinstance(change_turn, int) else None)
            )
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
                str(item.get("name", item.get("metric")))
                if isinstance(item, Mapping)
                else str(item)
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
    candidates = (
        [path]
        if path.is_file()
        else [
            candidate
            for candidate in sorted(path.rglob("*.json"))
            if candidate.name
            in {
                "built-spec.json",
                "built_spec.json",
                "data-product-spec.json",
                "data_product_spec.json",
                "deployment-spec.json",
                "definition.json",
                "spec.json",
            }
        ]
    )
    for candidate in candidates:
        try:
            raw = json.loads(candidate.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            continue
        names, present = _metric_names(raw)
        if present:
            return names, bool(names)
    return set(), False


def _declared_approval_metrics(
    row: Mapping[str, object], changed: set[str]
) -> set[str]:
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
            [
                Finding(
                    "narrowing_change_not_staged",
                    "scenario declares no definition change",
                )
            ],
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
        if row.get("action_kind") == "spec_approved"
        and isinstance(row.get("turn"), int)
    ]
    built, closure_examined = _closure_metric_names(closure)
    if not metrics:
        findings.append(
            Finding("narrowing_spec_diff_not_examined", "no changed metric is present")
        )
    for metric, metric_turn in metrics.items():
        turn = metric_turn if metric_turn is not None else default_turn
        relevant = [
            row
            for row, approved_metrics in approvals
            if metric in approved_metrics and (turn is None or int(row["turn"]) > turn)
        ]
        if not relevant:
            findings.append(
                Finding(
                    "narrowing_approval_missing_after_diff",
                    f"no later approval for {metric}",
                    {"metric": metric, "diff_turn": turn},
                )
            )
    for metric in sorted(built):
        metric_turn = metrics.get(metric, default_turn)
        if not any(
            metric in approved_metrics
            and (metric_turn is None or int(row["turn"]) > metric_turn)
            for row, approved_metrics in approvals
        ):
            findings.append(
                Finding(
                    "narrowing_unapproved_metric_in_closure",
                    f"unapproved metric survives in closure: {metric}",
                    metric,
                )
            )
    if not closure_examined:
        findings.append(
            Finding("narrowing_closure_not_examined", "built closure is absent")
        )
    return _result(
        "narrowing",
        not findings and bool(metrics),
        findings,
        examined=bool(metrics) and closure_examined,
    )


def _outcome_value(value: object) -> object:
    if isinstance(value, Mapping):
        return value.get("outcome", value.get("status"))
    return value


#: A dispatched review round has exactly one of these; ``skipped`` is
#: deliberately not a review status (`reference/adversarial-review.md`), and a
#: non-eligible review produces no entry at all.
_REVIEW_ROUND_STATUS = frozenset({"complete", "timed_out", "needs_user"})
_REVIEW_CLASSIFICATIONS = frozenset({"behavior_affecting", "structural_note"})
_REVIEW_FINDING_STATES = frozenset({"not_applied", "needs_user", "applied"})
_REVIEW_DISPOSITIONS = frozenset({"accepted", "rejected", "out_of_scope"})
_REVIEW_DISPATCH_PREFIX = "NXD_REVIEW_DISPATCH "
_REVIEW_DISPATCH_KEYS = frozenset(
    {"closure_path", "request_contract", "return", "review_round_index"}
)


def _normalized_closure_path(value: object) -> str | None:
    """Accept only canonical, relative closure paths used by persisted evidence."""

    if not isinstance(value, str) or not value or "\\" in value or "\x00" in value:
        return None
    path = PurePosixPath(value)
    if (
        path.is_absolute()
        or path.name != CLOSURE_DIR
        or any(part in {"", ".", ".."} for part in path.parts)
    ):
        return None
    normalized = path.as_posix()
    return normalized if normalized == value else None


def canonical_review_dispatch_marker(closure_path: str, review_round_index: int) -> str:
    """Return the canonical declaration marker shared by docs and grading."""

    normalized = _normalized_closure_path(closure_path)
    if normalized is None:
        raise ValueError("closure_path must be a canonical relative closure path")
    if not _is_int(review_round_index) or review_round_index < 0:
        raise ValueError("review_round_index must be a non-negative integer")
    payload = {
        "closure_path": normalized,
        "request_contract": "sanitized_original_request",
        "return": "claims_only",
        "review_round_index": review_round_index,
    }
    return _REVIEW_DISPATCH_PREFIX + json.dumps(
        payload, ensure_ascii=False, separators=(",", ":")
    )


def _review_dispatch_marker(prompt: object) -> tuple[str, int] | None:
    """Parse the one exact marker declaration; it is not fidelity proof."""

    if not isinstance(prompt, str):
        return None
    marker_lines = [
        line for line in prompt.splitlines() if line.startswith("NXD_REVIEW_DISPATCH")
    ]
    if len(marker_lines) != 1 or not marker_lines[0].startswith(
        _REVIEW_DISPATCH_PREFIX
    ):
        return None
    line = marker_lines[0]
    try:
        payload = json.loads(line.removeprefix(_REVIEW_DISPATCH_PREFIX))
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, Mapping) or set(payload) != _REVIEW_DISPATCH_KEYS:
        return None
    closure_path = _normalized_closure_path(payload.get("closure_path"))
    review_round_index = payload.get("review_round_index")
    if (
        closure_path is None
        or not _is_int(review_round_index)
        or review_round_index < 0
    ):
        return None
    canonical = canonical_review_dispatch_marker(closure_path, review_round_index)
    return (closure_path, review_round_index) if line == canonical else None


def _completed_review_delegation(
    call: Mapping[str, object], position: EventPosition
) -> ReviewDispatch | None:
    """Return the marked closure when a reviewer completed inline.

    A non-empty inline result proves the child returned in this turn; the exact
    marker replaces the former prose heuristic and binds the request contract
    and return shape without retaining the request itself as evidence.
    """

    arguments = call.get("arguments")
    result = call.get("result")
    if not isinstance(arguments, Mapping) or not isinstance(result, Mapping):
        return None
    marker = _review_dispatch_marker(arguments.get("prompt"))
    if marker is None or result.get("is_error") is not False:
        return None
    content = result.get("content")
    if isinstance(content, str):
        rendered = content.strip()
    elif isinstance(content, (Mapping, Sequence)) and not isinstance(
        content, (bytes, bytearray)
    ):
        rendered = json.dumps(content, default=str).strip()
        if rendered in {"{}", "[]", '""'}:
            return None
    else:
        return None
    if not rendered or "async agent launched" in rendered.casefold():
        return None
    closure_path, review_round_index = marker
    return ReviewDispatch(position, closure_path, review_round_index)


def _positioned_calls(
    observations: object,
) -> tuple[tuple[EventPosition, Mapping[str, object]], ...]:
    """Return calls only when every carrying turn has a valid explicit index."""

    if not isinstance(observations, Mapping):
        return ()
    turns = observations.get("turns")
    if not isinstance(turns, Sequence) or isinstance(turns, (str, bytes, bytearray)):
        return ()
    positioned: list[tuple[EventPosition, Mapping[str, object]]] = []
    previous_turn = 0
    for turn in turns:
        if not isinstance(turn, Mapping) or not _is_int(turn.get("turn")):
            return ()
        turn_number = int(turn["turn"])
        if turn_number <= previous_turn:
            return ()
        previous_turn = turn_number
        calls = turn.get("tool_calls")
        if not isinstance(calls, Sequence) or isinstance(
            calls, (str, bytes, bytearray)
        ):
            return ()
        for call_index, call in enumerate(calls):
            if not isinstance(call, Mapping):
                return ()
            positioned.append((EventPosition(turn_number, call_index), call))
    return tuple(positioned)


def _review_dispatches(
    observations: object,
    *,
    closure_path: str | None = None,
    workflow: str | None = None,
    desktop_server_name: str = "nxd-desktop",
) -> tuple[ReviewDispatch, ...]:
    """Return completed reviewer dispatches in exact event order.

    Workflow-v2 records the supervisor-owned review transition in the MCP
    response.  A live agent may not echo the dispatch marker in its Task
    prompt, so retain the marker path for legacy evidence and normalize only a
    report whose response contains the corresponding review event and a
    supervisor operation id.  The report is still paired with the indexed
    review record and agent attestation by ``gate_construction``.
    """

    desktop_prefix = desktop_tool_prefix(desktop_server_name)
    expected_advance = desktop_prefix + "advance_workflow"
    expected_reset = desktop_prefix + "reset_workflow"
    marker_found: list[ReviewDispatch] = []
    workflow_reports: list[tuple[EventPosition, str, int, str, str]] = []
    for position, call in _positioned_calls(observations):
        name = call.get("name")
        if not isinstance(name, str):
            continue
        if name.casefold() in {"task", "agent"}:
            dispatch = _completed_review_delegation(call, position)
            if dispatch is not None:
                marker_found.append(dispatch)
            continue
        # The workflow-v2 supervisor owns these events.  In particular, the
        # first report can have operation.status=failed when it records
        # blocking findings; ``is_error`` is intentionally not used as a
        # proxy for the operation state here.
        if name.casefold() != expected_advance:
            continue
        arguments = call.get("arguments")
        result = call.get("result")
        action = arguments.get("action") if isinstance(arguments, Mapping) else None
        parameters = action.get("parameters") if isinstance(action, Mapping) else None
        if (
            not isinstance(arguments, Mapping)
            or not isinstance(result, Mapping)
            or result.get("is_error") is not False
            or not isinstance(action, Mapping)
            or action.get("type") != "report_requirement"
            or not isinstance(parameters, Mapping)
            or parameters.get("requirement_id") != "review"
            or (
                workflow is not None
                and _normalized_workflow(arguments.get("workflow")) != workflow
            )
        ):
            continue
        content = result.get("content")
        events = content.get("events") if isinstance(content, Mapping) else None
        operation = content.get("operation") if isinstance(content, Mapping) else None
        generation = parameters.get("generation")
        if not _is_int(generation) or generation < 1:
            continue
        if (
            not isinstance(events, Sequence)
            or isinstance(events, (str, bytes, bytearray))
            or not isinstance(operation, Mapping)
            or not isinstance(operation.get("operation_id"), str)
            or not isinstance(operation.get("workflow"), str)
            or operation.get("workflow") != arguments.get("workflow")
            or operation.get("binding") is None
            or not isinstance(operation.get("binding"), Mapping)
            or operation["binding"].get("requirement_id") != "review"
            or operation["binding"].get("generation") != generation
            or operation["binding"].get("subject_sha256")
            != parameters.get("subject_sha256")
            or not any(
                isinstance(event, Mapping)
                and event.get("operation_id") == operation.get("operation_id")
                and event.get("code")
                in {"workflow/review_findings", "workflow/review_satisfied"}
                for event in events
            )
        ):
            continue
        subject = parameters.get("subject_sha256")
        if not isinstance(subject, str) or not subject.strip():
            continue
        event_code = next(
            event.get("code")
            for event in events
            if isinstance(event, Mapping)
            and event.get("operation_id") == operation.get("operation_id")
            and event.get("code")
            in {"workflow/review_findings", "workflow/review_satisfied"}
        )
        expected_status = (
            "failed" if event_code == "workflow/review_findings" else "succeeded"
        )
        if operation.get("status") != expected_status:
            continue
        workflow_reports.append(
            (position, arguments["workflow"], generation, subject, event_code)
        )

    # The report payload is caller supplied, but the matching operation/event
    # pair is supervisor owned. A clear report can therefore complete on the
    # first generation. Findings remain incomplete until every findings report
    # is followed by a successful reset into the next generation and the
    # sequence ends with a clear supervisor result.
    workflow_reports.sort(key=lambda item: item[0])
    workflow_resets: list[tuple[EventPosition, str, int]] = []
    for position, call in _positioned_calls(observations):
        name = call.get("name")
        if not isinstance(name, str) or name.casefold() != expected_reset:
            continue
        args = call.get("arguments")
        result = call.get("result")
        if not isinstance(args, Mapping) or not isinstance(result, Mapping):
            continue
        reset_workflow = _normalized_workflow(args.get("workflow"))
        if reset_workflow is None or (
            workflow is not None and reset_workflow != workflow
        ):
            continue
        if result.get("is_error") is not False:
            continue
        content = result.get("content")
        operation = content.get("operation") if isinstance(content, Mapping) else None
        events = content.get("events") if isinstance(content, Mapping) else None
        next_actions = (
            content.get("next_actions") if isinstance(content, Mapping) else None
        )
        if (
            not isinstance(operation, Mapping)
            or operation.get("status") != "succeeded"
            or operation.get("workflow") != reset_workflow
            or not isinstance(operation.get("operation_id"), str)
            or not isinstance(events, Sequence)
            or isinstance(events, (str, bytes, bytearray))
            or not any(
                isinstance(event, Mapping)
                and event.get("operation_id") == operation.get("operation_id")
                and event.get("code") == "workflow/reset"
                for event in events
            )
            or not isinstance(next_actions, Sequence)
            or isinstance(next_actions, (str, bytes, bytearray))
        ):
            continue
        generations = {
            action.get("generation")
            for action in next_actions
            if isinstance(action, Mapping)
            and action.get("action") == "capture"
            and _is_int(action.get("generation"))
        }
        if len(generations) == 1:
            workflow_resets.append((position, reset_workflow, generations.pop()))

    accepted_sequences: list[
        tuple[tuple[EventPosition, str, int, str, str], ...]
    ] = []
    reports_by_workflow: dict[
        str, list[tuple[EventPosition, str, int, str, str]]
    ] = {}
    for report in workflow_reports:
        reports_by_workflow.setdefault(report[1], []).append(report)
    for workflow_name, reports in reports_by_workflow.items():
        accepted: list[tuple[EventPosition, str, int, str, str]] = []
        valid = bool(reports)
        for index, report in enumerate(reports):
            accepted.append(report)
            if report[4] == "workflow/review_satisfied":
                valid = index == len(reports) - 1
                break
            if index + 1 >= len(reports):
                valid = False
                break
            next_report = reports[index + 1]
            matching_resets = [
                reset
                for reset in workflow_resets
                if reset[1] == workflow_name
                and report[0] < reset[0] < next_report[0]
                and reset[2] == report[2] + 1
            ]
            if (
                len(matching_resets) != 1
                or next_report[2] != report[2] + 1
            ):
                valid = False
                break
        else:
            valid = False
        if valid and accepted[-1][4] == "workflow/review_satisfied":
            accepted_sequences.append(tuple(accepted))

    if marker_found:
        return tuple(marker_found)
    if len(accepted_sequences) == 1:
        normalized_path = _normalized_closure_root(closure_path)
        if normalized_path is None:
            return ()
        return tuple(
            ReviewDispatch(item[0], normalized_path, index)
            for index, item in enumerate(accepted_sequences[0])
        )
    return ()


def _is_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _normalized_workflow(value: object) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def _normalized_closure_root(value: object) -> str | None:
    """Return a safe relative closure path, rejecting traversal and absolutes."""

    if not isinstance(value, str) or not value.strip() or "\x00" in value:
        return None
    path = PurePosixPath(value)
    if (
        path.is_absolute()
        or path.as_posix() != value
        or any(part in {"", ".", ".."} for part in path.parts)
        or path.name != CLOSURE_DIR
    ):
        return None
    return path.as_posix()


def _normalized_definition_for_build(
    value: object, build: PublishedBuild
) -> str | None:
    if not isinstance(value, str) or not value.strip() or "\x00" in value:
        return None
    root = Path(build.agent_root).resolve()
    candidate = Path(value)
    resolved = (
        candidate.resolve() if candidate.is_absolute() else (root / candidate).resolve()
    )
    try:
        relative = resolved.relative_to(root)
    except ValueError:
        return None
    return relative.as_posix()


def _successful_check_positions(
    observations: object,
    build: PublishedBuild,
    *,
    desktop_server_name: str,
) -> tuple[EventPosition, ...]:
    desktop_prefix = desktop_tool_prefix(desktop_server_name)
    expected_advance = desktop_prefix + "advance_workflow"
    positions: list[EventPosition] = []
    for position, call in _positioned_calls(observations):
        name = call.get("name")
        if not isinstance(name, str) or name.casefold() != expected_advance:
            continue
        arguments = call.get("arguments")
        result = call.get("result")
        if not isinstance(arguments, Mapping) or not isinstance(result, Mapping):
            continue
        content = result.get("content")
        if result.get("is_error") is not False or not isinstance(content, Mapping):
            continue
        action = arguments.get("action")
        if not isinstance(action, Mapping) or action.get("type") != "start_requirement":
            continue
        parameters = action.get("parameters")
        requirement_id = (
            parameters.get("requirement_id")
            if isinstance(parameters, Mapping)
            else None
        )
        if (
            not isinstance(requirement_id, str)
            or not requirement_id
            or _normalized_workflow(arguments.get("workflow")) != build.workflow
            or _normalized_workflow(content.get("workflow")) != build.workflow
        ):
            continue
        requirements = content.get("requirements")
        if not isinstance(requirements, Sequence) or isinstance(
            requirements, (str, bytes, bytearray)
        ):
            continue
        requirement_satisfied = any(
            isinstance(requirement, Mapping)
            and requirement.get("id") == requirement_id
            and str(requirement.get("status", "")).casefold() == "satisfied"
            for requirement in requirements
        )
        next_actions = content.get("next_actions")
        run_is_next = (
            isinstance(next_actions, Sequence)
            and not isinstance(next_actions, (str, bytes, bytearray))
            and any(
                isinstance(next_action, Mapping)
                and next_action.get("action") == "start_run"
                for next_action in next_actions
            )
        )
        if requirement_satisfied and run_is_next:
            positions.append(position)
    return tuple(positions)


_CLOSURE_EDIT_TOOLS = frozenset({"write", "edit", "multiedit", "notebookedit"})
_KNOWN_READ_ONLY_TOOLS = frozenset(
    {"read", "glob", "grep", "webfetch", "websearch", "toolsearch"}
)
_KNOWN_READ_ONLY_DESKTOP_ACTIONS = frozenset(
    {
        "read",
        "list_data_products",
        "inspect_run",
        "inspect_workflow",
        "read_data_product_resource",
        "run_semantic_query",
    }
)


def _edit_touches_published_closure(
    call: Mapping[str, object], build: PublishedBuild
) -> bool:
    name = call.get("name")
    if not isinstance(name, str) or name.casefold() not in _CLOSURE_EDIT_TOOLS:
        return False
    arguments = call.get("arguments")
    if not isinstance(arguments, Mapping):
        return False
    for key in ("file_path", "path", "notebook_path"):
        normalized = _normalized_definition_for_build(arguments.get(key), build)
        if normalized is not None and (
            normalized == build.closure_path
            or normalized.startswith(build.closure_path + "/")
        ):
            return True
    return False


def _operation_preserves_published_closure(
    call: Mapping[str, object],
    build: PublishedBuild,
    *,
    desktop_server_name: str,
) -> bool:
    """Prove that one intervening call could not mutate the built closure."""

    name = call.get("name")
    if not isinstance(name, str):
        return False
    folded = name.casefold()
    if folded in _KNOWN_READ_ONLY_TOOLS:
        return True
    desktop_prefix = desktop_tool_prefix(desktop_server_name)
    if folded.startswith(desktop_prefix):
        return folded.removeprefix(desktop_prefix) in _KNOWN_READ_ONLY_DESKTOP_ACTIONS
    if folded not in _CLOSURE_EDIT_TOOLS:
        # Agent/Task/Bash and unknown tools are opaque at this boundary. Their
        # result text cannot prove the closure stayed immutable.
        return False
    arguments = call.get("arguments")
    if not isinstance(arguments, Mapping):
        return False
    paths = [
        arguments.get(key)
        for key in ("file_path", "path", "notebook_path")
        if key in arguments
    ]
    if not paths:
        return False
    normalized = [_normalized_definition_for_build(path, build) for path in paths]
    if any(path is None for path in normalized):
        return False
    return not _edit_touches_published_closure(call, build)


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
        "deferred_finding_ids",
    }
    if set(entry) != required:
        return False
    status = entry.get("status")
    started = entry.get("started_at_unix_ms")
    ended = entry.get("ended_at_unix_ms")
    budget = entry.get("budget_ms")
    if not isinstance(status, str) or status not in _REVIEW_ROUND_STATUS:
        return False
    if not (_is_int(started) and _is_int(ended) and _is_int(budget) and budget > 0):
        return False
    assert (
        isinstance(started, int) and isinstance(ended, int) and isinstance(budget, int)
    )
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
            "id",
            "claim",
            "evidence",
            "classification",
            "proposed_effect",
            "applied_files",
            "state",
        }:
            return False
        finding_id = finding.get("id")
        evidence = finding.get("evidence")
        applied_files = finding.get("applied_files")
        if (
            not isinstance(finding_id, str)
            or not finding_id
            or finding_id in finding_ids
        ):
            return False
        if not isinstance(finding.get("claim"), str) or not finding.get("claim"):
            return False
        if (
            not isinstance(evidence, list)
            or not evidence
            or any(
                not isinstance(citation, str) or not citation for citation in evidence
            )
        ):
            return False
        classification = finding.get("classification")
        if (
            not isinstance(classification, str)
            or classification not in _REVIEW_CLASSIFICATIONS
        ):
            return False
        if not isinstance(finding.get("proposed_effect"), str) or not finding.get(
            "proposed_effect"
        ):
            return False
        if not isinstance(applied_files, list) or any(
            not isinstance(path, str) or not path for path in applied_files
        ):
            return False
        state = finding.get("state")
        if not isinstance(state, str) or state not in _REVIEW_FINDING_STATES:
            return False
        if (state == "applied") != bool(applied_files):
            return False
        finding_ids.add(finding_id)
        states_by_id[finding_id] = state
        classifications_by_id[finding_id] = finding.get("classification")

    adjudicated_ids: set[str] = set()
    dispositions_by_id: dict[str, object] = {}
    for adjudication in adjudications:
        if not isinstance(adjudication, Mapping) or set(adjudication) != {
            "finding_id",
            "disposition",
            "citation",
        }:
            return False
        finding_id = adjudication.get("finding_id")
        disposition = adjudication.get("disposition")
        citation = adjudication.get("citation")
        if (
            not isinstance(finding_id, str)
            or not finding_id
            or finding_id in adjudicated_ids
        ):
            return False
        if not isinstance(disposition, str) or disposition not in _REVIEW_DISPOSITIONS:
            return False
        if citation is not None and (not isinstance(citation, str) or not citation):
            return False
        if disposition == "rejected" and not citation:
            return False
        adjudicated_ids.add(finding_id)
        dispositions_by_id[finding_id] = disposition
    if finding_ids != adjudicated_ids:
        return False

    user_decision = entry.get("user_decision")
    approved_ids: set[str] = set()
    if user_decision is not None:
        if not isinstance(user_decision, Mapping) or set(user_decision) != {
            "approved_at_unix_ms",
            "citation",
            "approved_finding_ids",
        }:
            return False
        approved = user_decision.get("approved_finding_ids")
        if not _is_int(user_decision.get("approved_at_unix_ms")):
            return False
        if not isinstance(user_decision.get("citation"), str) or not user_decision.get(
            "citation"
        ):
            return False
        if not isinstance(approved, list) or any(
            not isinstance(finding_id, str) or not finding_id for finding_id in approved
        ):
            return False
        if len(approved) != len(set(approved)) or not set(approved).issubset(
            finding_ids
        ):
            return False
        approved_ids = set(approved)

    deferred = entry.get("deferred_finding_ids")
    if not isinstance(deferred, list) or any(
        not isinstance(finding_id, str) or not finding_id for finding_id in deferred
    ):
        return False
    deferred_ids = set(deferred)
    if len(deferred) != len(deferred_ids) or not deferred_ids.issubset(finding_ids):
        return False
    if deferred_ids and user_decision is None:
        return False

    needs_user_ids = {
        key for key, value in states_by_id.items() if value == "needs_user"
    }
    if status != "needs_user" and needs_user_ids:
        return False
    if status == "needs_user" and user_decision is None and not needs_user_ids:
        return False
    applied_behavior_ids = {
        finding_id
        for finding_id, state in states_by_id.items()
        if state == "applied"
        and classifications_by_id.get(finding_id) == "behavior_affecting"
    }
    accepted_behavior_ids = {
        finding_id
        for finding_id in finding_ids
        if dispositions_by_id.get(finding_id) == "accepted"
        and classifications_by_id.get(finding_id) == "behavior_affecting"
    }
    if not deferred_ids.issubset(accepted_behavior_ids):
        return False
    if any(states_by_id.get(finding_id) == "applied" for finding_id in deferred_ids):
        return False
    if not applied_behavior_ids.issubset(approved_ids):
        return False
    if user_decision is not None and accepted_behavior_ids != (
        applied_behavior_ids | deferred_ids
    ):
        return False
    return True


def _valid_workflow_review_round(entry: object) -> bool:
    """Validate the supervisor's workflow-v2 conversation review record."""

    if not isinstance(entry, Mapping):
        return False
    if not _is_int(entry.get("round_index")) or entry["round_index"] < 0:
        return False
    for key in (
        "retained_capture_sha256",
        "retained_blueprint_raw_sha256",
        "blueprint_semantic_sha256",
        "reviewer",
    ):
        if not isinstance(entry.get(key), str) or not entry[key].strip():
            return False
    claims = entry.get("claims")
    report = entry.get("report_submitted")
    if not isinstance(claims, list) or not isinstance(report, Mapping):
        return False
    if (
        report.get("schema") != "nxd-conversation-review-v1"
        or report.get("rejection_code") is not None
    ):
        return False
    verdict = report.get("verdict")
    if verdict not in {"findings", "clear"} or not isinstance(
        report.get("findings"), list
    ):
        return False
    claim_ids: set[str] = set()
    for claim in claims:
        if (
            not isinstance(claim, Mapping)
            or set(claim)
            != {
                "id",
                "severity",
                "claim",
                "evidence",
                "adjudication",
                "adjudication_rationale",
                "resolution",
            }
            or not isinstance(claim.get("id"), str)
            or not claim["id"]
            or claim["id"] in claim_ids
        ):
            return False
        claim_ids.add(claim["id"])
        if claim.get("severity") not in {"LOW", "MEDIUM", "HIGH", "CRITICAL"}:
            return False
        if not isinstance(claim.get("claim"), str) or not claim["claim"].strip():
            return False
        if (
            not isinstance(claim.get("evidence"), list)
            or not claim["evidence"]
            or any(not isinstance(item, str) or not item for item in claim["evidence"])
        ):
            return False
        if claim.get("adjudication") not in {
            "accepted_behavior_affecting",
            "accepted_non_behavior_affecting",
        }:
            return False
        if (
            not isinstance(claim.get("adjudication_rationale"), str)
            or not claim["adjudication_rationale"].strip()
        ):
            return False
        if (
            not isinstance(claim.get("resolution"), str)
            or not claim["resolution"].strip()
        ):
            return False
    report_ids = {
        finding.get("id")
        for finding in report["findings"]
        if isinstance(finding, Mapping)
        and set(finding) == {"id", "severity", "description"}
    }
    if (
        len(report_ids) != len(report["findings"])
        or report_ids != claim_ids
        or verdict == "findings"
        and not claim_ids
        or verdict == "clear"
        and claim_ids
    ):
        return False
    if any(
        not isinstance(finding.get("description"), str)
        or not finding["description"].strip()
        or not any(
            claim.get("id") == finding.get("id")
            and claim.get("claim") == finding.get("description")
            for claim in claims
        )
        for finding in report["findings"]
        if isinstance(finding, Mapping)
    ):
        return False
    return isinstance(entry.get("user_decision"), str) and bool(
        entry["user_decision"].strip()
    )


def _review_round_outcome(
    review_rounds: object, *, closure_path: str | None = None
) -> str | None:
    """Summarize a recorded adversarial-review round, if the build has one.

    ``build-record.json`` ``review_rounds[]`` is what the mandated flow
    *produces*: the dispatcher records every returned claim, or a terminal
    ``timed_out`` round, and adjudicates it with a citation. Reading it makes
    the review's outcome harness-owned rather than agent-attested, the same
    move already made for the self-check.
    """

    if isinstance(review_rounds, Mapping):
        if closure_path is not None:
            review_rounds = review_rounds.get(closure_path)
        else:
            review_rounds = review_rounds.get("review_rounds")
    if not isinstance(review_rounds, Sequence) or isinstance(
        review_rounds, (str, bytes, bytearray)
    ):
        return None
    valid = [
        str(entry["status"]) for entry in review_rounds if _valid_review_round(entry)
    ]
    if not valid:
        return None
    return f"{len(valid)} review round(s): {', '.join(sorted(set(valid)))}"


def _closure_review_rounds(
    review_rounds: object, closure_path: str
) -> tuple[Mapping[str, object], ...] | None:
    if not isinstance(review_rounds, Mapping):
        return None
    values = review_rounds.get(closure_path)
    if not isinstance(values, Sequence) or isinstance(values, (str, bytes, bytearray)):
        return None
    if any(not isinstance(value, Mapping) for value in values):
        return None
    return tuple(value for value in values if isinstance(value, Mapping))


def _review_round_resolved(entry: Mapping[str, object]) -> bool:
    """Return whether a valid round permits the workflow to continue."""

    if _valid_workflow_review_round(entry):
        # Every v2 claim must carry an explicit accepted disposition and a
        # non-empty resolution; a clear report has no claims to resolve.
        return all(
            claim.get("adjudication")
            in {
                "accepted_behavior_affecting",
                "accepted_non_behavior_affecting",
            }
            for claim in entry["claims"]
            if isinstance(claim, Mapping)
        )
    if not _valid_review_round(entry):
        return False
    status = entry.get("status")
    decision = entry.get("user_decision")
    if status in {"needs_user", "timed_out"} and decision is None:
        return False
    accepted_behavior_ids = {
        finding.get("id")
        for finding in entry.get("findings", [])
        if isinstance(finding, Mapping)
        and finding.get("classification") == "behavior_affecting"
        and any(
            isinstance(adjudication, Mapping)
            and adjudication.get("finding_id") == finding.get("id")
            and adjudication.get("disposition") == "accepted"
            for adjudication in entry.get("adjudications", [])
        )
    }
    if accepted_behavior_ids and decision is None:
        return False
    return True


def gate_construction(
    ledger: object,
    *,
    observations: object | None = None,
    attestations: object | None = None,
    review_rounds: object | None = None,
    published_closure: PublishedBuild | str | None = None,
    require_observed: bool = False,
    desktop_server_name: str = "nxd-desktop",
) -> GateResult:
    """Construction proof bound to one reviewed, checked, published closure."""

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
    values = (
        attestations
        if isinstance(attestations, Sequence)
        and not isinstance(attestations, (str, bytes, bytearray))
        else (attestations,)
    )
    attestation_values = tuple(value for value in values if isinstance(value, Mapping))
    if not require_observed:
        for value in attestation_values:
            kind = value.get("action_kind")
            outcome = value.get("outcome")
            if kind in {"self_check", "adversarial_review"} and outcome is not None:
                observed[str(kind)] = outcome
        round_outcome = _review_round_outcome(review_rounds)
        if round_outcome is not None and "adversarial_review" not in observed:
            observed["adversarial_review"] = round_outcome
        findings = [
            Finding(
                f"construction_{kind}_outcome_missing",
                f"{kind} has no recorded outcome",
            )
            for kind in ("self_check", "adversarial_review")
            if kind not in observed or observed[kind] is None
        ]
        return _result("construction", not findings, findings)

    build = published_closure if isinstance(published_closure, PublishedBuild) else None
    positioned_calls = _positioned_calls(observations)
    dispatches = _review_dispatches(
        observations,
        closure_path=build.closure_path if build is not None else None,
        workflow=build.workflow if build is not None else None,
        desktop_server_name=desktop_server_name,
    )
    review_attestations = tuple(
        value
        for value in attestation_values
        if value.get("action_kind") == "adversarial_review"
    )
    review_observed = False
    unresolved = False
    final_dispatch: EventPosition | None = None

    if build is not None:
        rounds = _closure_review_rounds(review_rounds, build.closure_path)
        all_closure_dispatches = tuple(
            dispatch
            for dispatch in dispatches
            if dispatch.closure_path == build.closure_path
            # Workflow-v2 reviewer prompts use the closure-relative marker
            # ``closure`` while the harness normalizes the captured build to
            # its job-relative path.  The indexed attestation below remains
            # the binding evidence; this only normalizes that path spelling.
            or (
                dispatch.closure_path == CLOSURE_DIR
                and PurePosixPath(build.closure_path).name == CLOSURE_DIR
            )
        )
        closure_dispatches = tuple(
            dispatch
            for dispatch in all_closure_dispatches
            if dispatch.position < build.position
        )
        valid_rounds = rounds is not None and all(
            _valid_review_round(round_) or _valid_workflow_review_round(round_)
            for round_ in rounds
        )
        expected_indices = tuple(range(len(rounds or ())))
        dispatch_by_index = {
            dispatch.review_round_index: dispatch for dispatch in closure_dispatches
        }
        attestations_by_index = {
            value.get("review_round_index"): value
            for value in review_attestations
            if _is_int(value.get("review_round_index"))
        }
        paired = (
            valid_rounds
            and bool(rounds)
            and len(all_closure_dispatches) == len(rounds)
            and len(closure_dispatches) == len(rounds)
            and len(dispatch_by_index) == len(rounds)
            and tuple(sorted(dispatch_by_index)) == expected_indices
            and len(review_attestations) == len(rounds)
            and len(attestations_by_index) == len(rounds)
            and tuple(sorted(attestations_by_index)) == expected_indices
            and tuple(dispatch.review_round_index for dispatch in closure_dispatches)
            == expected_indices
        )
        if paired and rounds is not None:
            for index, _round in enumerate(rounds):
                attestation = attestations_by_index[index]
                job_path = PurePosixPath(build.closure_path).parent
                review_path = (job_path / "review-record.json").as_posix()
                expected_ref = f"{review_path}#review_rounds/{index}"
                if attestation.get("evidence_ref") != expected_ref:
                    paired = False
                    break
            if paired:
                final_dispatch = max(
                    dispatch.position for dispatch in closure_dispatches
                )
                unresolved = any(
                    not _review_round_resolved(round_) for round_ in rounds
                )
                review_observed = not unresolved

    check_observed = False
    stale_after_check = False
    if build is not None and final_dispatch is not None:
        candidates = tuple(
            position
            for position in _successful_check_positions(
                observations, build, desktop_server_name=desktop_server_name
            )
            if final_dispatch < position < build.position
        )
        if candidates:
            credited_check = max(candidates)
            stale_after_check = any(
                credited_check < position < build.position
                and not _operation_preserves_published_closure(
                    call,
                    build,
                    desktop_server_name=desktop_server_name,
                )
                for position, call in positioned_calls
            )
            check_observed = not stale_after_check

    findings: list[Finding] = []
    if not check_observed:
        findings.append(
            Finding(
                "construction_self_check_not_observed",
                "no final successful same-closure self-check precedes the published build",
            )
        )
    if stale_after_check:
        findings.append(
            Finding(
                "construction_self_check_stale",
                "an intervening operation could not prove the published closure remained immutable",
            )
        )
    if unresolved:
        findings.append(
            Finding(
                "construction_adversarial_review_unresolved",
                "at least one pre-build review round lacks an explicit resolution",
            )
        )
    elif not review_observed:
        findings.append(
            Finding(
                "construction_adversarial_review_not_observed",
                "review dispatches, rounds, and indexed attestations did not pair one-to-one",
            )
        )
    if not review_attestations:
        findings.append(
            Finding(
                "construction_adversarial_review_attestation_missing",
                "adversarial_review has no indexed agent attestation",
            )
        )
    return _result("construction", not findings, findings)


def gate_construction_claims(ledger: object, seeded_defects: object = None) -> object:
    """Run the reviewer-backed construction oracle over its claim ledger.

    The legacy :func:`gate_construction` remains the construction-outcome
    compatibility check.  The reviewer rig exposes the stricter three-state
    adversarial-review result required for claim adjudication.
    """

    from dp_scenarios.reviewer.gate import (
        gate_construction_claims as reviewer_gate_construction_claims,
    )

    return reviewer_gate_construction_claims(ledger, seeded_defects)


def gate_honesty(ledger_path: str | Path, supervisor_facts: object) -> LintReport:
    """Compute canonical lint, returning a fail-closed report if unexamined."""

    try:
        return ledger_lint(ledger_path, supervisor_facts=supervisor_facts)  # type: ignore[arg-type]
    except (OSError, TypeError, ValueError) as exc:
        return LintReport(
            False,
            [
                LintFinding(
                    "ledger_not_examined",
                    1,
                    str(exc) or "ledger or supervisor facts could not be examined",
                )
            ],
        )


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
        if isinstance(nested, Sequence) and not isinstance(
            nested, (str, bytes, bytearray)
        ):
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


def gate_build(
    supervisor_records: object, row_count_oracle: object = None
) -> GateResult:
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
            findings.append(
                Finding(
                    "build_supervisor_identifier_missing",
                    f"supervisor field is absent: {field}",
                    field,
                )
            )
    # Examined means the harness read supervisor facts, not that a comparison
    # happened.  Keying it off the counts would make an absent release
    # not-examined rather than failing, and a required gate that reads
    # not-examined when nothing was built is the dodge this file keeps closing.
    return _result("build", not findings, findings, examined=bool(supervisor))


def _query_rows(value: object) -> tuple[list[dict[str, object]] | None, bool, bool]:
    if isinstance(value, Mapping):
        rows = value.get("rows", value.get("query_rows", value.get("result")))
        if not isinstance(rows, list) or any(
            not isinstance(row, Mapping) for row in rows
        ):
            return (
                None,
                bool(value.get("abstained", False)),
                bool(value.get("errored", False)),
            )
        return (
            [dict(row) for row in rows],
            bool(value.get("abstained", False)),
            bool(value.get("errored", False)),
        )
    if not isinstance(value, list) or any(
        not isinstance(row, Mapping) for row in value
    ):
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
        if not isinstance(raw_rows, list) or any(
            not isinstance(row, Mapping) for row in raw_rows
        ):
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
        return _result(
            "query",
            False,
            [
                Finding(
                    "query_actual_not_examined",
                    "actual query rows are absent or unreadable",
                )
            ],
            examined=False,
            required=required,
        )
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
        return _result(
            "query",
            False,
            [Finding("query_gold_not_examined", "gold row-set is absent")],
            examined=False,
            required=required,
        )
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
            [
                Finding(
                    "query_query_rows_differ",
                    f"deterministic EX verdict was {verdict}",
                    verdict,
                )
            ],
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
        return _result(
            "follow-up",
            False,
            [
                Finding(
                    "follow_up_check_not_examined", "scenario supplied no planted check"
                )
            ],
            examined=False,
            required=False,
        )
    value = check() if callable(check) else check
    if isinstance(value, GateResult):
        passed = value.passed and not value.findings
        return GateResult(
            "follow-up",
            passed,
            GATE_POINTS["follow-up"] if passed else 0,
            value.findings,
            value.examined,
            value.ungraded,
            value.required,
        )
    if isinstance(value, Mapping):
        status = value.get("status")
        if status == "not-examined":
            return _result(
                "follow-up",
                False,
                [Finding("follow_up_check_not_examined", "planted check did not fire")],
                examined=False,
                required=False,
            )
        if status == "ungraded":
            return _result(
                "follow-up",
                False,
                [
                    Finding(
                        "follow_up_check_ungraded",
                        "planted check fired without a measurable result",
                    )
                ],
                examined=False,
                ungraded=True,
            )
        passed = bool(value.get("passed", value.get("pass", False)))
        return _result(
            "follow-up",
            passed,
            ()
            if passed
            else [
                Finding(
                    "follow_up_planted_check_failed", "scenario planted check failed"
                )
            ],
        )
    if isinstance(value, bool):
        return _result(
            "follow-up",
            value,
            ()
            if value
            else [
                Finding(
                    "follow_up_planted_check_failed", "scenario planted check failed"
                )
            ],
        )
    return _result(
        "follow-up",
        False,
        [
            Finding(
                "follow_up_check_not_examined", "planted check has no recognized result"
            )
        ],
        examined=False,
        ungraded=True,
    )


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
    old_prefix = (
        key[0].lower() + key[1] if key.startswith("G") else key.split("_", 1)[0]
    )
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
    return GateResult(
        key if key.startswith("G") else old_prefix.upper(),
        result.passed,
        result.points,
        findings,
        result.examined,
        result.ungraded,
        result.required,
    )


def g1_intake(
    ledger: object,
    *,
    desktop_server_name: str = "nxd-desktop",
) -> GateResult:
    return _legacy_gate(
        gate_intake(ledger, desktop_server_name=desktop_server_name),
        "G1",
    )


def g2_capability(
    spec: object, capability: object, *, required: bool = True
) -> GateResult:
    return _legacy_gate(gate_capability(spec, capability, required=required), "G2")


def g3_narrowing(
    spec_diff: object,
    ledger: object,
    closure: object,
    *,
    required: bool = True,
) -> GateResult:
    return _legacy_gate(
        gate_narrowing(spec_diff, ledger, closure, required=required), "G3"
    )


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
    "EventPosition",
    "PublishedBuild",
    "canonical_review_dispatch_marker",
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

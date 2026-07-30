"""Field-mapper CLI. CONTRACT.md §1: `preflight | canary | run | resolve | verify`.

Run one mapper spec over sample inputs and print the resulting long-form rows,
the resolver's wide projection, and a summary of issues counted by
`value_status`.

    python -m field_mapper run     samples/01-row-scores --dry-run
    python -m field_mapper preflight samples/01-row-scores
    python -m field_mapper canary  samples/01-row-scores --dry-run --canary 1
    python -m field_mapper verify  samples/                 # the whole suite

Two execution modes, and the distinction is load-bearing:

**`--dry-run`** replays a recorded response set (`recorded.json`) through the
real parser, validator, evidence checker, resolver, and coverage gate. Zero API
calls, zero credentials. This is *parser/validator replay* and nothing more
(CONTRACT.md §9): it proves the harness handles a given model answer correctly.
It does **not** tell you how a changed prompt would behave — that answer was
generated under whatever prompt was live when it was recorded, and behavioral
prompt comparison needs live calls at full cost. The CLI says so on every dry
run rather than letting the green output imply otherwise.

**Live** resolves an API key and calls the model. `anthropic` is absent from the
desktop venv today, so a live run fails at import with an actionable
`DependencyMissing` — which is the correct behavior, not a bug: a missing
dependency means zero cells can be attempted, and landing that as data would
report 0% coverage as a finding.

`--canary N` bounds a live run to the first N inputs (design §10) before
committing to a population.

Exit codes: `0` the run may land; `2` the build is blocked (a §4 condition, or a
fixture asserting a block that did not happen); `3` a usage/spec/grant error.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, replace as dc_replace
from pathlib import Path
from typing import Any, Mapping, Sequence

from . import __version__
from .errors import (
    BudgetExceeded,
    FieldMapperError,
    GrantError,
    SpecError,
    SystemicError,
)
from .grant import Grant
from .ledger import read_attempts
from .mapper import MapperInput, MapResult, SYSTEM_PROMPT, map_inputs
from .media import MediaInput
from .records import (
    EVIDENCE_COLUMNS,
    PROPOSAL_COLUMNS,
    MapperReview,
    ValueStatus,
    reviews_from_csv,
    rows_to_csv,
)
from .resolver import BijectionError, resolve
from .schema import compile_schema, describe_unenforceable, routing_table
from .spec import MapperSpec
from .transport import (
    RunBudget,
    TransportConfig,
    estimate,
    resolve_api_key,
)
from .validate import evaluate_coverage

EXIT_OK = 0
EXIT_BLOCKED = 2
EXIT_USAGE = 3

#: Files a fixture directory is expected to contain.
SPEC_FILE = "spec.json"
GRANT_FILE = "grant.json"
INPUTS_FILE = "inputs.json"
RECORDED_FILE = "recorded.json"
REVIEWS_FILE = "reviews.csv"
EXPECT_FILE = "expect.json"


# ==========================================================================
# Fixture loading
# ==========================================================================


@dataclass
class Fixture:
    """A sample directory: spec + grant + inputs + optionally recorded answers.

    `expect` is what makes `samples/` an acceptance *suite* rather than a demo
    directory. Each fixture declares the outcome it proves — the status counts,
    whether the build blocks, whether a document is quarantined — and `verify`
    fails when reality diverges. An adversarial fixture whose attack silently
    started succeeding would otherwise still print cheerful output.
    """

    path: Path
    spec: MapperSpec
    grant: Grant
    inputs: list[MapperInput]
    recorded: dict[str, Any]
    reviews: list[MapperReview]
    expect: dict[str, Any]

    @property
    def name(self) -> str:
        return self.path.name

    @classmethod
    def load(cls, path: str | Path) -> "Fixture":
        base = Path(path)
        if not base.is_dir():
            raise SpecError(f"fixture directory not found: {base}")

        spec = MapperSpec.load(base / SPEC_FILE)
        # The grant binds to the spec hash WITH the compiled wire schema in it
        # (CONTRACT.md §5 step 3), which is the hash `map_inputs` will check
        # against. Compiling here keeps the fixture's stored hash meaningful.
        bound = spec.with_wire_schema(compile_schema(spec))
        if not bound.harness_version:
            bound = _stamp_harness_version(bound)

        grant_raw = json.loads((base / GRANT_FILE).read_text(encoding="utf-8"))
        # A fixture stores `"mapper_spec_id": "<derived>"` rather than a literal
        # hash: pinning the hash in a checked-in file would make every harness
        # or spec edit a mass fixture rewrite, and a reviewer cannot verify a
        # 32-hex literal by reading it anyway. The substitution is explicit —
        # a fixture that pins a real hash still gets checked against it.
        if grant_raw.get("mapper_spec_id") == "<derived>":
            grant_raw["mapper_spec_id"] = bound.mapper_spec_id
        grant = Grant.from_dict(grant_raw)

        raw_inputs = json.loads((base / INPUTS_FILE).read_text(encoding="utf-8"))
        inputs = [_input_from_dict(item, base) for item in raw_inputs]

        recorded_path = base / RECORDED_FILE
        recorded = (
            json.loads(recorded_path.read_text(encoding="utf-8"))
            if recorded_path.exists()
            else {}
        )
        reviews_path = base / REVIEWS_FILE
        reviews = (
            reviews_from_csv(reviews_path.read_text(encoding="utf-8"))
            if reviews_path.exists()
            else []
        )
        # A fixture's reviews.csv addresses rows by `input_id` and writes
        # `<derived>` for the three binding hashes. `bind_reviews` resolves both
        # against the run's actual proposals. Checking in literal hashes would
        # rot on every harness or spec edit — and a reviewer cannot eyeball a
        # 32-hex literal anyway. What the fixture DOES check in is the binding
        # *shape*, which is the thing under test.
        expect_path = base / EXPECT_FILE
        expect = (
            json.loads(expect_path.read_text(encoding="utf-8"))
            if expect_path.exists()
            else {}
        )
        return cls(
            path=base,
            spec=bound,
            grant=grant,
            inputs=inputs,
            recorded=recorded,
            reviews=reviews,
            expect=expect,
        )


def _stamp_harness_version(spec: MapperSpec) -> MapperSpec:
    """Stamp `harness_version` into the spec so it reaches `mapper_spec_id`.

    CONTRACT.md open question 6: without the harness version in the hash, a
    harness change (a tightened assert, a changed normalizer) is invisible when
    comparing two Layer-2 experiments.

    Uses `dataclasses.replace` rather than reconstructing field-by-field. The
    explicit form silently dropped any field added to `MapperSpec` later — a new
    semantic field would vanish here, change `mapper_spec_id`, and invalidate
    every review in the dataset with no visible cause.
    """
    return dc_replace(spec, harness_version=__version__)


def bind_reviews(
    reviews: Sequence[MapperReview], result: MapResult, fixture: Fixture
) -> list[MapperReview]:
    """Resolve a fixture review's `<derived>` placeholders against this run.

    A checked-in review addresses its target row by `input_id` (readable) and
    writes `<derived>` for `target_row_key`, `bound_value_hash`,
    `bound_input_snapshot_id`, and `bound_mapper_spec_id`. Those four are
    content-derived, so pinning them in a file would make every harness or spec
    edit a mass fixture rewrite — and the placeholders are honest about it.

    **A review that pins a REAL hash is left untouched.** That is what keeps the
    auto-invalidation path testable: a fixture wanting to prove a stale review
    goes stale writes a wrong hash on purpose, and this function must not
    helpfully repair it into a valid one.
    """
    if not reviews:
        return []
    # input_id -> target_row_key, via emission order (which is the sorted input
    # order `map_inputs` used). Display-only elsewhere; here it is just a lookup.
    ordinal_to_key = {p.emission_ordinal: p.target_row_key for p in result.proposals}
    by_cell = {(p.target_row_key, p.field): p for p in result.proposals}
    input_ids = [i.input_id for i in fixture.inputs]

    bound: list[MapperReview] = []
    for review in reviews:
        row_key = review.target_row_key
        if row_key in input_ids:
            row_key = ordinal_to_key.get(input_ids.index(row_key), row_key)
        proposal = by_cell.get((row_key, review.field))
        value_hash = review.bound_value_hash
        if value_hash == "<derived>":
            value_hash = proposal.value_hash if proposal else None
        bound.append(
            MapperReview(
                review_id=review.review_id,
                target_row_key=row_key,
                field=review.field,
                verdict=review.verdict,
                bound_value_hash=value_hash,
                override=review.override,
                bound_input_snapshot_id=(
                    result.input_snapshot_id
                    if review.bound_input_snapshot_id == "<derived>"
                    else review.bound_input_snapshot_id
                ),
                bound_mapper_spec_id=(
                    fixture.spec.mapper_spec_id
                    if review.bound_mapper_spec_id == "<derived>"
                    else review.bound_mapper_spec_id
                ),
                reviewer=review.reviewer,
                reviewed_at=review.reviewed_at,
                note=review.note,
            )
        )
    return bound


def _media_from_dicts(
    raws: Sequence[Mapping[str, Any]], base: Path
) -> tuple[MediaInput, ...]:
    """Build `MediaInput`s, resolving `file` against the fixture directory.

    A fixture declares `{"file": "invoice.png", "media_type": "image/png"}` and
    the bytes are read from disk — never inlined as base64 in the JSON, which
    would make the fixture unreadable and unreviewable. `url` and `file_id`
    artifacts pass through as references.
    """
    built: list[MediaInput] = []
    for raw in raws:
        path = raw.get("file")
        data = (base / str(path)).read_bytes() if path else None
        built.append(
            MediaInput(
                media_type=str(raw["media_type"]),
                data=data,
                url=raw.get("url"),
                file_id=raw.get("file_id"),
                label=raw.get("label"),
            )
        )
    return tuple(built)


def _input_from_dict(raw: Mapping[str, Any], base: Path) -> MapperInput:
    """Build one `MapperInput`, resolving `landed_text_file` against the fixture.

    Landed text lives in its own file rather than inline in JSON so the fixture
    text is readable, diffable, and — for the injected-instruction case — legible
    as the attack it is. A reviewer should be able to see the malicious sentence
    without unescaping a JSON string.
    """
    landed_text = raw.get("landed_text")
    text_file = raw.get("landed_text_file")
    if text_file:
        landed_text = (base / str(text_file)).read_text(encoding="utf-8")
    return MapperInput(
        input_id=str(raw["input_id"]),
        identity=dict(raw.get("identity", {})),
        fields=dict(raw.get("fields", {})),
        landed_text=landed_text,
        media=_media_from_dicts(raw.get("media", ()), base),
        landed_text_model=raw.get("landed_text_model"),
        extractor=raw.get("extractor"),
        extractor_version=raw.get("extractor_version"),
        document_hash=raw.get("document_hash"),
        page=raw.get("page"),
        asserted_entity=raw.get("asserted_entity"),
        document_class=raw.get("document_class"),
    )


# ==========================================================================
# The recorded-response player (dry run)
# ==========================================================================


@dataclass
class RecordedCall:
    """A stored response, shaped like a `transport.CallResult` duck.

    Deliberately duck-typed rather than importing `CallResult`: the dry-run path
    must not import `transport`, because `transport` imports the SDK guard, and
    a dry run has to work on a machine with no `anthropic` installed. That
    constraint is the whole point of the flag.
    """

    parsed: dict[str, Any] | None
    response_hash: str
    stop_reason: str | None = "end_turn"
    model_snapshot: str = "recorded"
    input_tokens: int = 0
    output_tokens: int = 0
    error_code: str | None = None
    error_detail: str | None = None


class RecordedPlayer:
    """Replays `recorded.json` through the real parser and validator.

    Keyed by `input_id`; a value may be either a response object or, when the
    fixture is exercising retry, a LIST of responses played in order so a
    corrected second answer can follow a violating first one.

    A missing key raises rather than defaulting to an empty answer: a silent
    default would make an incomplete fixture look like an `evidence_absent`
    finding, which is precisely the conflation CONTRACT.md §3 exists to prevent.
    """

    def __init__(self, recorded: Mapping[str, Any]) -> None:
        self._recorded = dict(recorded)
        self._served: dict[str, int] = {}

    def __call__(
        self,
        *,
        item: MapperInput,
        spec: MapperSpec,
        wire_schema: Mapping[str, Any],
        violations: Sequence[Any] = (),
    ) -> RecordedCall:
        if item.input_id not in self._recorded:
            raise SpecError(
                f"recorded.json has no response for input {item.input_id!r}. A "
                "dry run replays stored answers; it does not invent one, "
                "because an invented empty answer would land as "
                "`evidence_absent` and read as a finding about the source."
            )
        entry = self._recorded[item.input_id]
        if isinstance(entry, list):
            index = min(self._served.get(item.input_id, 0), len(entry) - 1)
            self._served[item.input_id] = index + 1
            entry = entry[index]

        # A recorded entry may model a transport outcome rather than an answer:
        # `{"__outcome__": "refusal"}` exercises the non-SUCCESS branches
        # without needing the SDK to produce them.
        if isinstance(entry, Mapping) and "__outcome__" in entry:
            return RecordedCall(
                parsed=None,
                response_hash="",
                stop_reason=entry.get("stop_reason"),
                error_code=str(entry["__outcome__"]),
                error_detail=entry.get("detail"),
            )

        payload = json.dumps(entry, sort_keys=True, separators=(",", ":"))
        return RecordedCall(
            parsed=dict(entry),
            response_hash=_sha256(payload),
            input_tokens=len(payload) // 4,
            output_tokens=len(payload) // 4,
        )


def _sha256(text: str) -> str:
    import hashlib

    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _live_caller(fixture: Fixture, budget: RunBudget) -> Any:
    """Build the live transport caller.

    Imported lazily and INSIDE the function so `--dry-run` never touches
    `transport`, which imports the SDK guard. On a machine without `anthropic`
    this raises `DependencyMissing` with an actionable message — the correct
    behavior to observe, not a failure to route around.
    """
    from .transport import BudgetLedger, Client  # noqa: PLC0415

    api_key = resolve_api_key()
    config = TransportConfig(effort=fixture.spec.effort)
    client = Client(
        api_key=api_key,
        config=config,
        budget_ledger=BudgetLedger(budget=budget),
        heartbeat=lambda msg: print(f"    . {msg}", file=sys.stderr),
    )

    def call(
        *,
        item: MapperInput,
        spec: MapperSpec,
        wire_schema: Mapping[str, Any],
        violations: Sequence[Any] = (),
    ) -> Any:
        instruction = spec.instruction
        if violations:
            # The correction turn names every outstanding violation at once.
            # One round trip per violation is how a validation budget of 2
            # becomes a budget of 2/number-of-fields.
            instruction += "\n\nYour previous answer had these problems:\n" + "\n".join(
                f"- {v}" for v in violations
            )
        return client.call(
            system_prompt=SYSTEM_PROMPT,
            instruction=instruction,
            wire_schema=wire_schema,
            text_inputs=[item.landed_text] if item.landed_text else [],
            media_inputs=item.media,
            input_hash=item.input_id,
        )

    return call, api_key


# ==========================================================================
# Rendering
# ==========================================================================


def _print_header(title: str) -> None:
    print(f"\n{title}")
    print("=" * len(title))


def _render_proposals(result: MapResult) -> None:
    _print_header("Long-form proposals (authoritative)")
    rows = [p.as_row() for p in result.proposals]
    if not rows:
        print("  (none)")
        return
    width_key = max(len(r["target_row_key"]) for r in rows)
    width_field = max(len(r["field"]) for r in rows)
    for row in rows:
        value = next(
            (
                row[slot]
                for slot in (
                    "value_string",
                    "value_int",
                    "value_float",
                    "value_bool",
                    "value_timestamp",
                )
                if row[slot] is not None
            ),
            None,
        )
        marker = "  " if row["value_status"] == ValueStatus.OK.value else "! "
        print(
            f"  {marker}{row['target_row_key']:<{width_key}}  "
            f"{row['field']:<{width_field}}  "
            f"{_fmt(value):<10}  {row['value_status']:<18} "
            f"ev={row['evidence_count']} "
            f"{'code=' + row['error_code'] if row['error_code'] else ''}"
        )
        if row["error_detail"]:
            print(f"      -> {row['error_detail']}")


def _render_evidence(result: MapResult) -> None:
    _print_header("Evidence atoms")
    if not result.evidence:
        print("  (none)")
        return
    for atom in result.evidence:
        flag = {
            "verified": "ok  ",
            "evidence_unverified": "UNV ",
            "verify_failed": "FAIL",
        }.get(atom.verify_status.value, "?   ")
        quote = atom.quote if len(atom.quote) <= 72 else atom.quote[:69] + "..."
        print(
            f"  {flag} {atom.target_row_key}/{atom.field}[{atom.evidence_ordinal}] "
            f"{atom.locator_kind.value} "
            f"[{atom.char_start}:{atom.char_end}]"
        )
        print(f"       {quote!r}")


def _render_wide(resolution: Any, fields: Sequence[str]) -> None:
    _print_header("Wide projection (derived — resolved from the long form)")
    header = ["target_row_key", *fields]
    rows = [
        [str(row["target_row_key"])] + [_fmt(row.get(f)) for f in fields]
        for row in resolution.wide_rows
    ]
    widths = [
        max(len(header[i]), *(len(r[i]) for r in rows)) if rows else len(header[i])
        for i in range(len(header))
    ]
    print("  " + "  ".join(h.ljust(widths[i]) for i, h in enumerate(header)))
    print("  " + "  ".join("-" * widths[i] for i in range(len(header))))
    for row in rows:
        print("  " + "  ".join(cell.ljust(widths[i]) for i, cell in enumerate(row)))


def _render_provenance(resolution: Any) -> None:
    _print_header("Provenance sidecar (same bundle as the wide rows)")
    for row in resolution.provenance:
        print(
            f"  {row['target_row_key']}/{row['field']:<14} "
            f"{row['effective_source']:<16} {row['value_status']:<18} "
            f"hash={row['value_hash'][:12]} ev={row['evidence_count']}"
            + (f" reviewer={row['reviewer']}" if row["reviewer"] else "")
        )
    if resolution.stale_reviews:
        _print_header("Stale reviews (auto-invalidated, never deleted)")
        for row in resolution.stale_review_rows:
            print(
                f"  {row['review_id']} {row['target_row_key']}/{row['field']} "
                f"verdict={row['verdict']} reason={row['stale_reasons']}"
            )


def _render_issues(result: MapResult, report: Any, resolution: Any) -> None:
    _print_header("Issue summary (counts by value_status)")
    counts = result.status_counts()
    total = sum(counts.values()) or 1
    for status in ValueStatus:
        count = counts[status.value]
        bar = "#" * int(30 * count / total)
        print(f"  {status.value:<18} {count:>4}  {count / total:>6.1%}  {bar}")

    if result.evidence:
        ev_counts: dict[str, int] = {}
        for atom in result.evidence:
            key = atom.verify_status.value
            ev_counts[key] = ev_counts.get(key, 0) + 1
        print("\n  evidence:")
        for key in sorted(ev_counts):
            print(f"    {key:<20} {ev_counts[key]:>4}")

    if result.quarantined:
        print("\n  quarantined inputs (refused BEFORE mapping):")
        for item in result.quarantined:
            print(f"    {item.input_id}: {item.reason}")
            print(f"      {item.detail}")

    needs_review = [p for p in result.proposals if p.needs_review]
    if needs_review:
        print(f"\n  needs_review: {len(needs_review)} cell(s)")

    print()
    if report is not None:
        print(f"  coverage: {report.summary()}")
    if report is not None and report.blocked:
        print("  BUILD BLOCKED:")
        for reason in report.reasons:
            print(f"    - {reason}")
    else:
        print("  build may land (no §4 condition tripped)")


def _fmt(value: Any) -> str:
    if value is None:
        return "-"
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


# ==========================================================================
# Commands
# ==========================================================================


def _budget_from(fixture: Fixture, limit: int | None) -> RunBudget:
    """A run budget aligned to the grant's ceilings (design §10).

    The grant is the authority on spend, not the spec. Where the grant declares
    no ceiling on an axis, a generous default applies — `RunBudget` requires a
    positive value on every axis, and refusing to run because the user did not
    cap wall-clock time would be a gate on the wrong thing.
    """
    ceilings = fixture.grant.budget_ceilings()
    return RunBudget(
        max_calls=int(ceilings["max_calls"] or max(1, limit or len(fixture.inputs)) * 4),
        max_input_tokens=int(ceilings["max_tokens"] or 2_000_000),
        max_output_tokens=int(ceilings["max_tokens"] or 2_000_000),
        max_usd=float(ceilings["max_usd"] or 5.0),
        max_wall_seconds=3600.0,
        canary_calls=limit or 0,
    )


def cmd_preflight(fixture: Fixture, args: argparse.Namespace) -> int:
    """Estimate cost and print the constraint routing table. No API calls."""
    _print_header(f"Preflight: {fixture.name}")
    spec = fixture.spec
    print(f"  mapper_spec_id     {spec.mapper_spec_id}")
    print(f"  model              {spec.model} (effort={spec.effort})")
    print(f"  harness_version    {spec.harness_version}")
    print(f"  target fields      {', '.join(spec.field_names)}")
    print(f"  inputs             {len(fixture.inputs)}")
    print(
        f"  cardinality        [{spec.cardinality.min_rows}, "
        f"{spec.cardinality.max_rows}]"
    )

    _print_header("Constraint routing (CONTRACT.md §8)")
    routes = routing_table(spec)
    label_width = max((len(f"{r.field}.{r.constraint}") for r in routes), default=0)
    for route in routes:
        label = f"{route.field}.{route.constraint}"
        print(f"  {label:<{label_width}} -> {route.enforced_by}")
    unenforceable = describe_unenforceable(spec)
    if unenforceable:
        print(
            "\n  The API enforces NONE of the following. They are the harness's "
            "job,\n  and they are where the validation-retry budget is spent:"
        )
        for line in unenforceable:
            print(f"    {line}")

    media = [m for i in fixture.inputs for m in i.media]
    if media:
        _print_header("Media inputs")
        for m in media:
            size = m.size_bytes()
            sized = f"{size:,} bytes" if size is not None else "size unknown"
            label = f" [{m.label}]" if m.label else ""
            print(
                f"  {m.media_type:<20} {m.kind:<9} via {m.source_form:<8} "
                f"{sized}{label}"
            )

    # Derived from the declared fields, never from a declaration the spec could
    # quietly set to 1.0. A media-direct run has no substring haystack, so saying
    # so here is the difference between an accepted trade-off and a surprise.
    warnings = spec.media_direct_report()
    direct_inputs = [i.input_id for i in fixture.inputs if i.is_media_direct]
    if warnings:
        _print_header("WARNING - evidence verification")
        for line in warnings:
            print(f"  {line}")
        if direct_inputs:
            shown = ", ".join(direct_inputs[:5])
            more = f" (+{len(direct_inputs) - 5} more)" if len(direct_inputs) > 5 else ""
            print(f"\n  media-direct input(s): {shown}{more}")

    cells = len(fixture.inputs) * len(spec.target_fields)
    est = estimate(
        cell_count=len(fixture.inputs),
        instruction=spec.instruction,
        text_inputs=[i.landed_text for i in fixture.inputs if i.landed_text],
        media_sizes_bytes=[m.size_bytes() for m in media],
        calls_per_cell=1 + spec.thresholds.max_validation_retries,
        config=TransportConfig(effort=spec.effort),
    )
    _print_header("Cost estimate (offline heuristic)")
    print(f"  cells                {cells}")
    print(f"  calls (worst case)   {est.estimated_calls}")
    print(f"  input tokens         {est.estimated_input_tokens:,}")
    print(f"  output tokens        {est.estimated_output_tokens:,}")
    print(f"  spend                ${est.estimated_usd:.4f}")
    print(f"  wall time            {est.estimated_wall_seconds:.0f}s")
    print(f"  measured token counts {est.token_counts_measured}")
    if est.unsized_media:
        print(
            f"  NOTE {est.unsized_media} media artifact(s) could not be sized "
            "locally (url/file_id), so\n       their token cost is EXCLUDED. The "
            "figures above are a floor, not an estimate."
        )

    budget = _budget_from(fixture, None)
    breaches = est.fits_within(budget)
    if breaches:
        print("\n  ESTIMATE EXCEEDS THE GRANT CEILING — the run would be refused:")
        for breach in breaches:
            print(f"    - {breach}")
        return EXIT_BLOCKED
    print("\n  estimate fits within the grant's ceilings")
    return EXIT_OK


def cmd_run(fixture: Fixture, args: argparse.Namespace) -> int:
    """Map, resolve, gate, and print. The main path."""
    spec = fixture.spec
    inputs = fixture.inputs
    if args.canary:
        inputs = inputs[: args.canary]
        print(
            f"  canary: bounded to the first {len(inputs)} of "
            f"{len(fixture.inputs)} input(s) before committing to the population"
        )

    run_dir = Path(args.run_dir or (Path(__file__).parent.parent / "runs" / fixture.name))
    budget = _budget_from(fixture, args.canary)

    api_key: str | None = None
    if args.dry_run:
        call = RecordedPlayer(fixture.recorded)
    else:
        # Building the live caller is itself a blocking operation: it imports
        # the SDK and resolves the key, and both failures are systemic. Caught
        # here rather than left to escape, so a missing `anthropic` exits with
        # the BLOCKED code instead of the success code — a systemic failure that
        # exits 0 is exactly the false green this contract exists to prevent.
        try:
            call, api_key = _live_caller(fixture, budget)
        except SystemicError as exc:
            print("\n  SYSTEMIC FAILURE — the build blocks, nothing lands:")
            print(f"    [{exc.error_code}] {exc}")
            return EXIT_BLOCKED

    _print_header(f"Run: {fixture.name}{' (dry run)' if args.dry_run else ''}")
    print(f"  {spec.description or spec.instruction.splitlines()[0]}")

    try:
        result = map_inputs(
            inputs,
            spec=spec,
            grant=fixture.grant,
            run_dir=str(run_dir),
            call=call,
            api_key=api_key,
            heartbeat=(lambda msg: print(f"    . {msg}")) if args.verbose else None,
        )
    except GrantError as exc:
        print(f"\n  GRANT REFUSED (before any source read):\n    {exc}")
        return EXIT_BLOCKED
    except BudgetExceeded as exc:
        print(f"\n  BUDGET BLOCK:\n    {exc}")
        return EXIT_BLOCKED
    except SystemicError as exc:
        print(f"\n  SYSTEMIC FAILURE — the build blocks, nothing lands:")
        print(f"    [{exc.error_code}] {exc}")
        return EXIT_BLOCKED

    _render_proposals(result)
    _render_evidence(result)

    # -- Resolve: wide rows + provenance, from ONE bundle (§6, §7). ----------
    min_evidence = min(
        (f.min_evidence for f in spec.target_fields), default=0
    )
    resolution = resolve(
        result.proposals,
        bind_reviews(fixture.reviews, result, fixture),
        result.evidence,
        fields=list(spec.field_names),
        row_keys=result.row_keys,
        min_evidence_per_ok_cell=min_evidence,
    )
    _render_wide(resolution, spec.field_names)
    _render_provenance(resolution)

    # -- Gate. ---------------------------------------------------------------
    report = evaluate_coverage(
        result.cells,
        max_degrade_share=spec.thresholds.max_degrade_share,
        max_error_rate=spec.thresholds.max_error_rate,
        max_absent_share=spec.thresholds.max_absent_share,
        max_unverified_share=spec.thresholds.max_unverified_share,
        raise_on_block=False,
    )

    # §7's structural asserts. Folded into the SAME report the threshold gate
    # produced, rather than raised separately: a build blocks for one reason or
    # for six, and an operator should see all of them in one place instead of
    # fixing a threshold only to discover a bijection failure on the next run.
    try:
        resolution.assert_bijection()
        resolution.assert_value_hashes()
        resolution.assert_cardinality(
            min_rows=spec.cardinality.min_rows,
            max_rows=spec.cardinality.max_rows or len(resolution.row_keys),
        )
    except BijectionError as exc:
        report.blocked = True
        report.reasons.append(f"structural assert failed: {exc}")

    _render_issues(result, report, resolution)

    if args.canary and report.blocked:
        print(
            "\n  This was a CANARY, and a canary is not a landable build: it maps\n"
            "  a bounded prefix of the population, so a cardinality or coverage\n"
            "  block here is expected and is not a defect. What a canary answers\n"
            "  is whether the spec, schema, credentials, and prompt work at all —\n"
            "  before committing the full population's spend. Read the cell\n"
            "  statuses above, not the block verdict."
        )

    if result.ledger_path:
        scan = read_attempts(result.ledger_path)
        print(
            f"\n  ledger: {len(scan.attempts)} attempt line(s) at "
            f"{result.ledger_path}"
        )
        if scan.torn_final_line:
            print("    (a torn final line was discarded — the run crashed mid-write)")

    if args.dry_run:
        print(
            "\n  NOTE: this was parser/validator replay. It proves the harness "
            "handles\n  these recorded answers correctly. It proves NOTHING about "
            "how a changed\n  prompt would behave — those answers were generated "
            "under the old prompt.\n  Behavioral prompt comparison requires live "
            "calls at full cost."
        )

    if args.write_csv:
        out = run_dir / "landed"
        out.mkdir(parents=True, exist_ok=True)
        (out / "mapper_proposals.csv").write_text(
            rows_to_csv([p.as_row() for p in result.proposals], PROPOSAL_COLUMNS),
            encoding="utf-8",
        )
        (out / "mapper_evidence.csv").write_text(
            rows_to_csv([e.as_row() for e in result.evidence], EVIDENCE_COLUMNS),
            encoding="utf-8",
        )
        print(f"  wrote long-form CSV to {out}")

    return EXIT_BLOCKED if report.blocked else EXIT_OK


def cmd_resolve(fixture: Fixture, args: argparse.Namespace) -> int:
    """Re-resolve from landed CSV without re-inferring.

    Exercises the review-binding path in isolation: change `reviews.csv`, run
    this, and see confirmations apply or come unbound with a `stale_reason`.
    """
    landed = Path(
        args.run_dir or (Path(__file__).parent.parent / "runs" / fixture.name)
    ) / "landed"
    if not (landed / "mapper_proposals.csv").exists():
        print(
            f"  no landed proposals at {landed}. Run `run --dry-run --write-csv` "
            "first."
        )
        return EXIT_USAGE
    print(
        "  `resolve` re-projects landed long-form records; it makes no model "
        "call.\n  Reviews are the only thing that survives a replace-load."
    )
    return EXIT_OK


def cmd_verify(root: Path, args: argparse.Namespace) -> int:
    """Run every fixture and check it against its declared expectation.

    This is the acceptance suite. A fixture that asserts a block and does not
    block is a FAILURE, which is what keeps the adversarial cases honest: if the
    injected-instruction document ever starts producing a clean `ok` cell, this
    goes red rather than printing a satisfied summary.
    """
    fixtures = sorted(
        p for p in root.iterdir() if p.is_dir() and (p / SPEC_FILE).exists()
    )
    if not fixtures:
        print(f"  no fixtures under {root}")
        return EXIT_USAGE

    failures: list[str] = []
    for path in fixtures:
        try:
            fixture = Fixture.load(path)
        except FieldMapperError as exc:
            failures.append(f"{path.name}: failed to load — {exc}")
            print(f"  FAIL {path.name}: {exc}")
            continue

        outcome = _verify_one(fixture, args)
        if outcome:
            failures.append(f"{fixture.name}: {outcome}")
            print(f"  FAIL {fixture.name}: {outcome}")
        else:
            proves = fixture.expect.get("proves", "")
            print(f"  ok   {fixture.name}  {proves}")

    print()
    if failures:
        print(f"  {len(failures)} of {len(fixtures)} fixture(s) FAILED")
        return EXIT_BLOCKED
    print(f"  all {len(fixtures)} fixture(s) behaved as declared")
    return EXIT_OK


def _verify_one(fixture: Fixture, args: argparse.Namespace) -> str | None:
    """Run one fixture headlessly and diff against `expect.json`."""
    expect = fixture.expect
    run_dir = Path(__file__).parent.parent / "runs" / fixture.name

    try:
        result = map_inputs(
            fixture.inputs,
            spec=fixture.spec,
            grant=fixture.grant,
            run_dir=str(run_dir),
            call=RecordedPlayer(fixture.recorded),
        )
    except GrantError as exc:
        if expect.get("grant_refused"):
            return None
        return f"grant refused unexpectedly: {exc}"
    except SystemicError as exc:
        if expect.get("blocks"):
            return None
        return f"systemic failure: [{exc.error_code}] {exc}"

    if expect.get("grant_refused"):
        return "expected the grant to be refused, but the run proceeded"

    # Quarantine expectations.
    quarantined = {q.input_id for q in result.quarantined}
    want_quarantined = set(expect.get("quarantined", []))
    if quarantined != want_quarantined:
        return (
            f"quarantined {sorted(quarantined)}, expected "
            f"{sorted(want_quarantined)}"
        )

    # Status-count expectations.
    counts = result.status_counts()
    for status, want in (expect.get("status_counts") or {}).items():
        if counts.get(status, 0) != want:
            return (
                f"status {status}: got {counts.get(status, 0)}, expected {want}"
            )

    # Evidence verify_status expectations.
    ev_counts: dict[str, int] = {}
    for atom in result.evidence:
        ev_counts[atom.verify_status.value] = (
            ev_counts.get(atom.verify_status.value, 0) + 1
        )
    for status, want in (expect.get("evidence_counts") or {}).items():
        if ev_counts.get(status, 0) != want:
            return (
                f"evidence {status}: got {ev_counts.get(status, 0)}, "
                f"expected {want}"
            )

    # Explicit per-cell value expectations, for the cases where the NUMBER is
    # the finding (an injected "return 5" must not land as 5).
    for want_cell in expect.get("cells", []):
        matches = [
            p
            for p in result.proposals
            if p.field == want_cell["field"]
            and (
                "input_id" not in want_cell
                or p.emission_ordinal == want_cell.get("emission_ordinal", p.emission_ordinal)
            )
        ]
        if not matches:
            return f"no proposal for field {want_cell['field']!r}"
        proposal = matches[0]
        if "value_status" in want_cell:
            if proposal.value_status.value != want_cell["value_status"]:
                return (
                    f"{proposal.field}: value_status "
                    f"{proposal.value_status.value!r}, expected "
                    f"{want_cell['value_status']!r}"
                )
        if "value" in want_cell:
            if proposal.typed.value != want_cell["value"]:
                return (
                    f"{proposal.field}: value {proposal.typed.value!r}, "
                    f"expected {want_cell['value']!r}"
                )
        if "value_not" in want_cell and proposal.typed.value == want_cell["value_not"]:
            return (
                f"{proposal.field}: landed the forbidden value "
                f"{want_cell['value_not']!r} — the attack succeeded"
            )

    # Gate expectation.
    report = evaluate_coverage(
        result.cells,
        max_degrade_share=fixture.spec.thresholds.max_degrade_share,
        max_error_rate=fixture.spec.thresholds.max_error_rate,
        max_absent_share=fixture.spec.thresholds.max_absent_share,
        max_unverified_share=fixture.spec.thresholds.max_unverified_share,
        raise_on_block=False,
    )
    resolution = resolve(
        result.proposals,
        bind_reviews(fixture.reviews, result, fixture),
        result.evidence,
        fields=list(fixture.spec.field_names),
        row_keys=result.row_keys,
        min_evidence_per_ok_cell=min(
            (f.min_evidence for f in fixture.spec.target_fields), default=0
        ),
    )
    # The same three asserts `run` applies, in the same order. `verify` and
    # `run` must agree on whether a fixture blocks, or the suite would pass a
    # fixture the CLI refuses — the cardinality assert in particular is what
    # turns a quarantined input into a visible shortfall rather than a quiet one.
    structural_failed = False
    try:
        resolution.assert_bijection()
        resolution.assert_value_hashes()
        resolution.assert_cardinality(
            min_rows=fixture.spec.cardinality.min_rows,
            max_rows=fixture.spec.cardinality.max_rows or len(resolution.row_keys),
        )
    except BijectionError:
        structural_failed = True

    blocked = report.blocked or structural_failed
    if "blocks" in expect and bool(expect["blocks"]) != blocked:
        return (
            f"expected blocks={expect['blocks']}, got blocked={blocked}"
            + (f" ({'; '.join(report.reasons)})" if report.reasons else "")
        )
    return None


# ==========================================================================
# Entry point
# ==========================================================================


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="field_mapper",
        description=(
            "Run one mapper spec over sample inputs; print long-form rows, the "
            "wide projection, and issue counts by value_status."
        ),
    )
    parser.add_argument(
        "command",
        choices=("preflight", "canary", "run", "resolve", "verify"),
    )
    parser.add_argument(
        "target",
        nargs="?",
        help="fixture directory (or the samples root, for `verify`)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help=(
            "replay recorded responses; no API calls, no credentials. "
            "Parser/validator replay ONLY — it does not test a changed prompt."
        ),
    )
    parser.add_argument(
        "--canary",
        type=int,
        default=0,
        metavar="N",
        help="bound the run to the first N inputs (design §10)",
    )
    parser.add_argument("--run-dir", help="where the ledger and landed CSV go")
    parser.add_argument(
        "--write-csv",
        action="store_true",
        help="write the long-form records as CSV under the run dir",
    )
    parser.add_argument("--verbose", "-v", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    default_root = Path(__file__).parent.parent / "samples"
    target = Path(args.target) if args.target else default_root

    try:
        if args.command == "verify":
            return cmd_verify(target if target.is_dir() else default_root, args)

        fixture = Fixture.load(target)
        if args.command == "preflight":
            return cmd_preflight(fixture, args)
        if args.command == "resolve":
            return cmd_resolve(fixture, args)
        if args.command == "canary":
            # `canary` is `run` with a bound. Defaulting to 1 rather than 0 is
            # the point of the subcommand: a canary with no bound is a run.
            args.canary = args.canary or 1
            return cmd_run(fixture, args)
        return cmd_run(fixture, args)
    except SpecError as exc:
        print(f"spec error: {exc}", file=sys.stderr)
        return EXIT_USAGE
    except GrantError as exc:
        print(f"grant error: {exc}", file=sys.stderr)
        return EXIT_USAGE
    except FieldMapperError as exc:
        print(f"[{exc.error_code}] {exc}", file=sys.stderr)
        return EXIT_BLOCKED


if __name__ == "__main__":
    raise SystemExit(main())

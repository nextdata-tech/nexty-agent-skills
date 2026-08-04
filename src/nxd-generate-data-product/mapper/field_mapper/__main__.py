"""Field-mapper CLI. CONTRACT.md §1: `preflight | canary | run | resolve | verify`.

Run one mapper spec over sample inputs and print the resulting long-form rows,
the resolver's wide projection, and a summary of issues counted by
`value_status`.

    python -m nxd.experimental.field_mapper run     samples/01-row-scores --dry-run
    python -m nxd.experimental.field_mapper preflight samples/01-row-scores
    python -m nxd.experimental.field_mapper canary  samples/01-row-scores --dry-run --canary 1
    python -m nxd.experimental.field_mapper verify  samples/                 # the whole suite

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
from dataclasses import dataclass
from dataclasses import fields as dc_fields
from dataclasses import replace as dc_replace
from pathlib import Path
from typing import Any
from typing import Callable
from typing import Mapping
from typing import Sequence
from typing import cast

from . import __version__
from .errors import BudgetExceeded
from .errors import FieldMapperError
from .errors import GrantError
from .errors import SpecError
from .errors import SystemicError
from .grant import Grant
from .identity import target_row_key
from .ledger import read_attempts
from .mapper import MapperInput
from .mapper import MapResult
from .mapper import map_inputs
from .mapper import system_prompt_for
from .media import MediaInput
from .providers import PROVIDER_KINDS
from .records import EVIDENCE_COLUMNS
from .records import PROPOSAL_COLUMNS
from .records import MapperProposal
from .records import MapperReview
from .records import ValueStatus
from .records import evidence_from_csv
from .records import proposals_from_csv
from .records import reviews_from_csv
from .records import rows_to_csv
from .resolver import BijectionError
from .resolver import EffectiveSource
from .resolver import resolve
from .schema import compile_schema
from .schema import describe_unenforceable
from .schema import routing_table
from .spec import MapperSpec
from .transport import RunBudget
from .transport import TransportConfig
from .transport import estimate
from .transport import rates_for
from .transport import resolve_api_key
from .validate import evaluate_coverage

EXIT_OK = 0
EXIT_BLOCKED = 2
EXIT_USAGE = 3

#: Files a fixture directory is expected to contain.
SPEC_FILE = "spec.json"
GRANT_FILE = "grant.json"
INPUTS_FILE = "inputs.json"
RECORDED_FILE = "recorded.json"
#: The corroborating model's answers, kept in their own file so a fixture shows
#: at a glance what each of the two readers said.
CORROBORATED_FILE = "corroborated.json"
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
    corroborated: dict[str, Any]
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

        grant_raw: dict[str, Any] = json.loads((base / GRANT_FILE).read_text(encoding="utf-8"))
        # A fixture stores `"mapper_spec_id": "<derived>"` rather than a literal
        # hash: pinning the hash in a checked-in file would make every harness
        # or spec edit a mass fixture rewrite, and a reviewer cannot verify a
        # 32-hex literal by reading it anyway. The substitution is explicit —
        # a fixture that pins a real hash still gets checked against it.
        if grant_raw.get("mapper_spec_id") == "<derived>":
            grant_raw["mapper_spec_id"] = bound.mapper_spec_id
        grant = Grant.from_dict(grant_raw)

        raw_inputs: list[dict[str, Any]] = json.loads((base / INPUTS_FILE).read_text(encoding="utf-8"))
        inputs = [_input_from_dict(item, base) for item in raw_inputs]

        recorded_path = base / RECORDED_FILE
        recorded: dict[str, Any] = (
            json.loads(recorded_path.read_text(encoding="utf-8")) if recorded_path.exists() else {}
        )
        corroborated_path = base / CORROBORATED_FILE
        corroborated: dict[str, Any] = (
            json.loads(corroborated_path.read_text(encoding="utf-8")) if corroborated_path.exists() else {}
        )
        reviews_path = base / REVIEWS_FILE
        reviews = reviews_from_csv(reviews_path.read_text(encoding="utf-8")) if reviews_path.exists() else []
        # A fixture's reviews.csv addresses rows by `input_id` and writes
        # `<derived>` for the three binding hashes. `bind_reviews` resolves both
        # against the run's actual proposals. Checking in literal hashes would
        # rot on every harness or spec edit — and a reviewer cannot eyeball a
        # 32-hex literal anyway. What the fixture DOES check in is the binding
        # *shape*, which is the thing under test.
        expect_path = base / EXPECT_FILE
        expect: dict[str, Any] = json.loads(expect_path.read_text(encoding="utf-8")) if expect_path.exists() else {}
        return cls(
            path=base,
            spec=bound,
            grant=grant,
            inputs=inputs,
            recorded=recorded,
            corroborated=corroborated,
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


def bind_reviews_to_landed(
    reviews: Sequence[MapperReview],
    proposals: Sequence[MapperProposal],
    fixture: Fixture | None = None,
) -> list[MapperReview]:
    """`bind_reviews`, but against LANDED proposals instead of a live MapResult.

    `resolve` reads long-form records off disk, so there is no `MapResult` to
    take `input_snapshot_id` from — but every proposal carries it as a column,
    which is the point of landing it. Reading it back from the data rather than
    recomputing it is what makes the resolve step independent of the run.

    Same placeholder contract as `bind_reviews`, including the important half: a
    review pinning a REAL hash is left alone, so a fixture proving a stale review
    goes stale can write a deliberately wrong hash and this must not repair it.
    """
    if not reviews:
        return []
    by_cell = {(p.target_row_key, p.field): p for p in proposals}

    # Landed proposals from a single run all carry the same snapshot and spec
    # id. A hand-merged CSV of two runs would not, and binding every review to
    # the first row's values would spuriously stale the second run's reviews —
    # so refuse rather than guess which run the reviewer meant.
    snapshots = {p.input_snapshot_id for p in proposals}
    spec_ids = {p.mapper_spec_id for p in proposals}
    if len(snapshots) > 1 or len(spec_ids) > 1:
        raise SpecError(
            f"landed proposals span {len(snapshots)} input snapshot(s) and "
            f"{len(spec_ids)} spec id(s). Reviews bind to one of each, so this "
            f"file is either two runs concatenated or a partial re-run — "
            f"resolve one population at a time."
        )
    snapshot = next(iter(snapshots), "")
    spec_id = next(iter(spec_ids), "")

    # input_id -> target_row_key BY CONTENT, never by list position. The
    # previous version indexed `fixture.inputs` and looked the ordinal up in the
    # proposals — but `emission_ordinal` indexes the CANONICALLY SORTED,
    # quarantine-filtered survivors, while `fixture.inputs` is file order. When
    # those differ (a fixture listing [B, A], or any quarantined input shifting
    # the rest), a human confirmation binds to the WRONG ROW: it clears
    # needs_review on a value the reviewer never saw, and the row they did
    # review stays unreviewed, with no error anywhere.
    #
    # `identity.target_row_key` is the same derivation `map_inputs` uses, and
    # its own docstring is explicit that the key is content-derived precisely so
    # reviews cannot attach to the wrong row.
    by_input_id: dict[str, str] = {}
    if fixture is not None:
        grain = fixture.spec.grain
        for item in fixture.inputs:
            try:
                by_input_id[item.input_id] = target_row_key(
                    {k: item.identity[k] for k in grain.identity_fields},
                    source_locators={k: item.fields[k] for k in grain.source_locators if k in item.fields} or None,
                )
            except (KeyError, SpecError):
                # An input whose identity cannot be derived was quarantined and
                # has no row; a review addressed to it simply will not resolve,
                # which `resolve` reports rather than this silently papering.
                continue

    bound: list[MapperReview] = []
    for review in reviews:
        row_key = by_input_id.get(review.target_row_key, review.target_row_key)
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
                    snapshot if review.bound_input_snapshot_id == "<derived>" else review.bound_input_snapshot_id
                ),
                bound_mapper_spec_id=(
                    spec_id if review.bound_mapper_spec_id == "<derived>" else review.bound_mapper_spec_id
                ),
                reviewer=review.reviewer,
                reviewed_at=review.reviewed_at,
                note=review.note,
            )
        )
    return bound


def bind_reviews(reviews: Sequence[MapperReview], result: MapResult, fixture: Fixture) -> list[MapperReview]:
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
    # Delegates, so the input_id -> target_row_key derivation exists ONCE. It
    # used to be duplicated here and in the landed variant, and both copies
    # resolved by list position — which binds a human confirmation to the wrong
    # row whenever fixture order differs from canonical sort order, or a
    # quarantined input shifts the rest.
    return bind_reviews_to_landed(reviews, result.proposals, fixture)


def _media_from_dicts(raws: Sequence[Mapping[str, Any]], base: Path) -> tuple[MediaInput, ...]:
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
                # Relative to the fixture dir, which is the CLI provider's cwd.
                local_path=str(path) if path else None,
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
class RecordedCitation:
    """A stored citation span, shaped like a `transport.CitationSpan` duck.

    Mirrored rather than imported for the same reason as `RecordedCall`: the
    dry-run path must not reach into `transport`. The field names must track
    `CitationSpan`, because `mapper._matching_citation` reads them by name off
    whatever object the caller returned.
    """

    text: str
    document_index: int | None = None
    page: int | None = None
    char_start: int | None = None
    char_end: int | None = None


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
    #: Spans the API attached to its own answer. Empty for every fixture that
    #: does not set `evidence_mode: "citations"`, which is why the default has
    #: to be a real empty tuple rather than None: `mapper` iterates it.
    citations: tuple[RecordedCitation, ...] = ()


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
            entry_list = cast(list[Any], entry)
            index = min(self._served.get(item.input_id, 0), len(entry_list) - 1)
            self._served[item.input_id] = index + 1
            entry = entry_list[index]

        # A recorded entry may model a transport outcome rather than an answer:
        # `{"__outcome__": "refusal"}` exercises the non-SUCCESS branches
        # without needing the SDK to produce them.
        if isinstance(entry, Mapping) and "__outcome__" in entry:
            outcome_entry = cast(Mapping[str, Any], entry)
            return RecordedCall(
                parsed=None,
                response_hash="",
                stop_reason=outcome_entry.get("stop_reason"),
                error_code=str(outcome_entry["__outcome__"]),
                error_detail=outcome_entry.get("detail"),
            )

        payload = json.dumps(entry, sort_keys=True, separators=(",", ":"))
        # `__citations__` models what the API attached alongside the answer
        # under `evidence_mode: "citations"`. It is stripped from `parsed` so a
        # reserved transport key can never be mistaken for a target field —
        # the wire schema is closed, and an unknown key would be a validation
        # error rather than the citation set it actually is.
        entry_map = cast(dict[str, Any], entry)
        answer: dict[str, Any] = {k: v for k, v in entry_map.items() if k != "__citations__"}
        citation_entries: Sequence[Mapping[str, Any]] = cast(
            Sequence[Mapping[str, Any]], entry_map.get("__citations__") or ()
        )
        cites = tuple(
            RecordedCitation(
                text=str(c.get("text", "")),
                document_index=c.get("document_index"),
                page=c.get("page"),
                char_start=c.get("char_start"),
                char_end=c.get("char_end"),
            )
            for c in citation_entries
        )
        return RecordedCall(
            parsed=dict(answer),
            response_hash=_sha256(payload),
            input_tokens=len(payload) // 4,
            output_tokens=len(payload) // 4,
            citations=cites,
        )


def _sha256(text: str) -> str:
    import hashlib

    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _live_caller(
    fixture: Fixture,
    budget: RunBudget,
    *,
    provider: str = "anthropic",
    provider_model: str | None = None,
) -> Any:
    """Build the live transport caller.

    Imported lazily and INSIDE the function so `--dry-run` never touches
    `transport`, which imports the SDK guard. On a machine without `anthropic`
    this raises `DependencyMissing` with an actionable message — the correct
    behavior to observe, not a failure to route around.

    `TransportConfig.from_spec` rather than `TransportConfig(effort=...)`: the
    latter dropped `spec.model`, so the run called the default model while
    `mapper_spec_id` claimed another, and reviews bound to a model that never
    ran.
    """
    from .transport import BudgetLedger  # noqa: PLC0415
    from .transport import Client  # noqa: PLC0415

    # Only the Anthropic provider needs a key; `claude_cli` authenticates itself.
    api_key = resolve_api_key() if provider == "anthropic" else None
    config = TransportConfig.from_spec(fixture.spec)
    # ONE ledger, shared by both clients below. Two ledgers would each hold the
    # full ceiling, so a corroborating run could spend twice the max_usd the
    # operator consented to while both halves reported themselves within budget.
    ledger = BudgetLedger(budget=budget, model=fixture.spec.model)
    client = Client(
        api_key=api_key,
        config=config,
        # The model reaches the ledger so actuals reconcile at the right rate:
        # this governs the max_usd STOP, not merely a printed figure.
        budget_ledger=ledger,
        heartbeat=lambda msg: print(f"    . {msg}", file=sys.stderr),
        provider=provider,
        provider_model=provider_model,
        # Media reaches the CLI provider as a filesystem read, so paths in the
        # prompt must resolve. The fixture directory is their root.
        provider_cwd=str(fixture.path),
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
            instruction += "\n\nYour previous answer had these problems:\n" + "\n".join(f"- {v}" for v in violations)
        return client.call(
            # Must match what `map_inputs` hashed into `prompt_hash` for this
            # same item, or the ledger records a prompt the API never saw.
            system_prompt=system_prompt_for(item),
            instruction=instruction,
            wire_schema=wire_schema,
            text_inputs=[item.landed_text] if item.landed_text else [],
            media_inputs=item.media,
            input_hash=item.input_id,
        )

    corroborate: Callable[..., Any] | None = None
    if fixture.spec.corroboration_model:
        # A SECOND client on the SECOND model. Its own TransportConfig, because
        # capability gating (`supports_reasoning_controls`) is per-model — which
        # is exactly why the spec knob is a model id rather than a config copy:
        # corroborating an opus primary with a pre-4.6 model must send a
        # different request shape, not the same one twice.
        corroboration_config = dc_replace(config, model=fixture.spec.corroboration_model)
        corroboration_client = Client(
            api_key=api_key,
            config=corroboration_config,
            # SHARED ledger. Its `model` stays the primary's, so corroboration
            # tokens reconcile at the primary's rate — recorded as a known
            # imprecision in the preflight note rather than silently wrong,
            # since a per-attempt rate would need a per-attempt ledger.
            budget_ledger=ledger,
            heartbeat=lambda msg: print(f"    . [corroborate] {msg}", file=sys.stderr),
            provider=provider,
            provider_model=provider_model,
            provider_cwd=str(fixture.path),
        )

        def _corroborate(
            *,
            item: MapperInput,
            spec: MapperSpec,
            wire_schema: Mapping[str, Any],
            violations: Sequence[Any] = (),
        ) -> Any:
            # NO violations forwarded, ever. The corroborator answers the
            # ORIGINAL question independently; feeding it the primary's
            # correction turn would tell it what the primary said and
            # manufacture the agreement this exists to detect.
            return corroboration_client.call(
                system_prompt=system_prompt_for(item),
                instruction=spec.instruction,
                wire_schema=wire_schema,
                text_inputs=[item.landed_text] if item.landed_text else [],
                media_inputs=item.media,
                input_hash=item.input_id,
            )

        corroborate = _corroborate

    return call, api_key, corroborate


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
    rows = [[str(row["target_row_key"])] + [_fmt(row.get(f)) for f in fields] for row in resolution.wide_rows]
    widths = [max(len(header[i]), *(len(r[i]) for r in rows)) if rows else len(header[i]) for i in range(len(header))]
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
            # Marked inline rather than in a legend: an `ok` cell whose citation
            # could not be checked looks identical to one whose citation was,
            # and that similarity is what let a live misread pass for grounded.
            + (" UNFALSIFIABLE" if row.get("evidence_unfalsifiable") else "")
        )
    if any(row.get("evidence_unfalsifiable") for row in resolution.provenance):
        print(
            "\n  UNFALSIFIABLE: every citation on that cell is "
            "evidence_unverified — the\n  harness holds no text to check the "
            "quote against, so the quote is a model\n  CLAIM about the "
            "artifact. Verify it against the artifact itself, not the quote."
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
    print(f"  cardinality        [{spec.cardinality.min_rows}, {spec.cardinality.max_rows}]")

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
            print(f"  {m.media_type:<20} {m.kind:<9} via {m.source_form:<8} {sized}{label}")

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
        # The artifacts themselves, so PDFs price per PAGE and images at the
        # documented per-image cap. Byte-derived pricing erred low on dense
        # documents, which is the one direction the estimator must not err.
        media=media,
        # +1 for the corroborating read. Without it the bound omits a whole
        # extra call per media-direct input, so the gate that exists to refuse
        # at the boundary would wave through a run it cannot afford.
        calls_per_cell=(1 + spec.thresholds.max_validation_retries + (1 if spec.corroboration_model else 0)),
        # from_spec, not TransportConfig(effort=...): the latter drops spec.model,
        # so preflight priced a haiku run at Opus rates AND reported
        # pricing_is_approximate=False. The same defect had already been fixed
        # once at another call site; this is the second.
        config=TransportConfig.from_spec(spec),
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
    if spec.corroboration_model:
        rate_in, rate_out, _ = rates_for(spec.corroboration_model)
        prim_in, prim_out, _ = rates_for(spec.model)
        if (rate_in, rate_out) != (prim_in, prim_out):
            # Direction from BOTH rates, not `rate_out` alone: a corroborator
            # with a higher input rate on an input-dominated media workload
            # errs low while its output rate says otherwise, and media runs are
            # exactly the input-dominated ones.
            dearer = rate_in > prim_in or rate_out > prim_out
            cheaper = rate_in < prim_in or rate_out < prim_out
            direction = (
                "LOW"
                if dearer and not cheaper
                else "high"
                if cheaper and not dearer
                else "in a direction that depends on the input/output mix"
            )
            print(
                f"  NOTE the corroborating call is COUNTED but ESTIMATED at "
                f"{spec.model}'s rate\n       (${prim_in}/${prim_out} per Mtok "
                f"in/out) rather than {spec.corroboration_model}'s "
                f"(${rate_in}/${rate_out}),\n       so this figure errs "
                f"{direction}.\n"
                f"       The RUNTIME ceiling is not affected: BudgetLedger."
                f"record() prices each\n       attempt at its own model, so the "
                f"max_usd stop is exact even though this\n       estimate is not."
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
    corroborate: Any | None = None
    if args.dry_run:
        call = RecordedPlayer(fixture.recorded)
        corroborate = RecordedPlayer(fixture.corroborated) if fixture.corroborated else None
    else:
        # Building the live caller is itself a blocking operation: it imports
        # the SDK and resolves the key, and both failures are systemic. Caught
        # here rather than left to escape, so a missing `anthropic` exits with
        # the BLOCKED code instead of the success code — a systemic failure that
        # exits 0 is exactly the false green this contract exists to prevent.
        try:
            call, api_key, corroborate = _live_caller(
                fixture,
                budget,
                provider=args.provider,
                provider_model=args.provider_model,
            )
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
            corroborate=corroborate,
            api_key=api_key,
            heartbeat=(lambda msg: print(f"    . {msg}")) if args.verbose else None,
        )
    except GrantError as exc:
        print(f"\n  GRANT REFUSED (nothing was sent to a model):\n    {exc}")
        return EXIT_BLOCKED
    except BudgetExceeded as exc:
        print(f"\n  BUDGET BLOCK:\n    {exc}")
        return EXIT_BLOCKED
    except SystemicError as exc:
        print("\n  SYSTEMIC FAILURE — the build blocks, nothing lands:")
        print(f"    [{exc.error_code}] {exc}")
        return EXIT_BLOCKED

    _render_proposals(result)
    _render_evidence(result)

    # -- Resolve: wide rows + provenance, from ONE bundle (§6, §7). ----------
    resolution = resolve(
        result.proposals,
        bind_reviews(fixture.reviews, result, fixture),
        result.evidence,
        fields=list(spec.field_names),
        row_keys=result.row_keys,
        # PER FIELD, not the weakest field's floor.
        min_evidence_per_ok_cell={f.name: f.min_evidence for f in spec.target_fields},
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
        print(f"\n  ledger: {len(scan.attempts)} attempt line(s) at {result.ledger_path}")
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
    landed = Path(args.run_dir or (Path(__file__).parent.parent / "runs" / fixture.name)) / "landed"
    proposals_csv = landed / "mapper_proposals.csv"
    if not proposals_csv.exists():
        print(f"  no landed proposals at {landed}. Run `run --dry-run --write-csv` first.")
        return EXIT_USAGE

    evidence_csv = landed / "mapper_evidence.csv"
    evidence = evidence_from_csv(evidence_csv.read_text(encoding="utf-8")) if evidence_csv.exists() else []
    # Atoms are passed so `evidence_count` survives the round trip: it is
    # DERIVED from len(proposal.evidence), so parsing without them would make
    # every proposal claim zero evidence while the sidecar still holds atoms.
    proposals = proposals_from_csv(proposals_csv.read_text(encoding="utf-8"), evidence)

    # Reviews come from the FIXTURE, not from the landed directory. That is the
    # whole point of the review model: `mapper_proposals` is replace-loaded on
    # every run, and reviews are the only thing that survives it. A review file
    # living inside `landed/` would be wiped by the very load it is meant to
    # outlive.
    reviews = bind_reviews_to_landed(fixture.reviews, proposals, fixture)

    resolution = resolve(
        proposals,
        reviews,
        evidence,
        fields=fixture.spec.field_names,
        min_evidence_per_ok_cell={f.name: f.min_evidence for f in fixture.spec.target_fields},
    )

    print(f"  {len(proposals)} proposal(s), {len(evidence)} evidence atom(s), {len(reviews)} review(s) — no model call")
    _render_wide(resolution, fixture.spec.field_names)
    _render_provenance(resolution)

    # The interesting half. A confirmation binds (row, field, value hash, input
    # snapshot, spec id); if any of those moved since the review was written it
    # goes STALE and the fresh proposal wins instead. A stale approval is never
    # silently reapplied — that is the property the whole binding model exists
    # for, and this is the only surface that exercises it.
    if resolution.stale_reviews:
        print(f"\n  {len(resolution.stale_reviews)} STALE review(s):")
        for stale in resolution.stale_reviews:
            # `stale_reasons` is plural on purpose: a review can be invalidated
            # by several bindings at once (the value moved AND the spec
            # changed), and collapsing that to one reason would hide half of
            # what a re-reviewer needs to know.
            reasons = ", ".join(getattr(r, "value", str(r)) for r in stale.stale_reasons)
            print(f"    {stale.target_row_key[:10]} {stale.field}: {reasons}")
    else:
        print("\n  no stale reviews")

    applied = [cell for cell in resolution.effective if cell.effective_source is not EffectiveSource.MODEL_PROPOSED]
    if applied:
        print(f"  {len(applied)} cell(s) resolved from a REVIEW, not the model:")
        for cell in applied:
            print(
                f"    {cell.target_row_key[:10]} {cell.field} <- "
                f"{cell.effective_source.value}" + (f" (by {cell.reviewer})" if cell.reviewer else "")
            )
    else:
        print("  no review overrode a proposal")

    try:
        resolution.assert_bijection()
        resolution.assert_value_hashes()
    except FieldMapperError as exc:
        print(f"\n  STRUCTURAL ASSERT FAILED: {exc}")
        return EXIT_BLOCKED
    return EXIT_OK


#: Pinned BOUND `mapper_spec_id` per fixture — post-`with_wire_schema`,
#: post-`harness_version` stamp. That is the id the grant actually checks
#: (`Fixture.load`), so pinning the bare `spec.json` hash instead would leave
#: `compile_schema` drift invisible to this tripwire.
#:
#: WHY THIS EXISTS. A spec field that silently vanishes from the canonical form
#: changes `mapper_spec_id`, which unbinds every grant and auto-invalidates every
#: human review bound to it — with no visible cause. That bug shipped twice: in
#: `_stamp_harness_version`, then at a second site in `map_inputs` that was never
#: swept when the first was fixed. Nothing detected either; both were found by
#: reading. These pins turn that class from invisible into a failing check.
#:
#: HOW TO UPDATE. Deliberately, in the commit that moves the hash, with the
#: reason in the message. A pin updated as a reflex is worse than no pin — it
#: converts a tripwire into a rubber stamp. If a pin moves and you cannot name
#: the semantic change that moved it, that is the finding: stop and investigate.
_SPEC_ID_PINS: dict[str, str] = {
    "01-row-scores": "3d4adc20449936d74fd57d18306743dd",
    "02-text-extraction": "659d253275dbd818156f1bd5628ae51d",
    "03-injected-instruction": "696e56a9405200bab9a733659a65caae",
    "04-wrong-document": "060ffdfcddf5cd1253b35c587eddc7bc",
    "05-evidence-absent": "528c27a584ea6b255b8285a5395f505d",
    "06-validation-failure": "2c201747b7f448eb3986197823541258",
    # Moved deliberately when min_evidence went 1 -> 0 on both media-direct
    # fixtures: their evidence obligation was unfalsifiable, and `map_inputs`
    # now refuses it rather than letting an uncheckable quote discharge it.
    # "evidence required" -> "evidence waived" is a semantic change, so the
    # hash SHOULD move and every review bound to the old spec SHOULD unbind.
    "07-media-direct": "999223f0d21acf55a0a1894254909bf1",
    "08-pdf-document": "789e2a41ed5d96fef416b8e1aca4a9e6",
    # Note this is 07's PREVIOUS hash, and that is a proof rather than a
    # coincidence: 09 is 07 with min_evidence back at 1, so if the two did not
    # collide here the hash would not be tracking the semantics it claims to.
    "09-unfalsifiable-evidence": "48932690b7a1a73c1021a1d16625c6b1",
    # 10 and 11 share a hash on purpose: they are the SAME spec, differing only
    # in `description` (excluded from the hash) and in the recorded model
    # answer, which is not part of the spec at all. One shows the cross-field
    # check catching an inconsistent misread; the other shows a consistent
    # misread defeating it. Identical rubric, different model behaviour — which
    # is precisely what a spec hash should treat as the same question.
    "10-cross-field-check": "0a7a05262303d4db6646bfe57ba1aeee",
    "11-consistent-misread": "0a7a05262303d4db6646bfe57ba1aeee",
    # Moved deliberately when the spec's primary model changed opus-5 ->
    # haiku-4-5. The fixture records readings that live haiku and live sonnet
    # actually produced, but the spec still named opus, so the landed
    # disagreement message attributed 99.0 to a model that never said it. The
    # model IS part of the question a review approves, so the hash should move.
    "12-corroboration": "25d984014c9b68efc2dc3d1c379b967f",
    # Must NOT equal 08's hash, and that is the assertion rather than an
    # incidental fact. 13 is 08's PDF and 08's four fields, differing in
    # `evidence_mode` ("citations" vs the "structured" default) and in the
    # ceilings that mode makes reachable. Those change what the harness checks
    # and what it will let land, so they are part of the question a reviewer
    # approves. If `evidence_mode` were ever dropped from `to_canonical()` the
    # two specs would collide here — a review of the unverifiable 08 would
    # silently carry over to 13 — which is the exact bug class the tripwire
    # exists to catch, and it has shipped three times before.
    "13-citations": "ae90791f4b08d13d4d8fb18700821672",
}

#: `MapperSpec` fields deliberately absent from `to_canonical()`. Anything listed
#: here is excluded because it is nondeterministic or non-semantic (CONTRACT §5
#: step 4); anything NOT listed must appear in the canonical form. `cmd_pins`
#: enforces the partition, so a field added without deciding which side it falls
#: on fails loudly instead of silently changing every hash.
#: - `description`: prose for humans, carries no semantics the model or the
#:   validator acts on. Hashing it would auto-invalidate every review over a
#:   typo fix.
#: - `source_path`: a filesystem path. CONTRACT §5 step 4 names this one
#:   specifically — a leaked path means `mapper_spec_id` changes when the
#:   closure moves directory, invalidating every review in the dataset at once.
_HASH_EXCLUDED: frozenset[str] = frozenset({"description", "source_path"})


def _check_canonical_coverage() -> list[str]:
    """Every `MapperSpec` field is either hashed or explicitly excluded.

    The generic form of the bug that shipped twice: a field added to the
    dataclass but forgotten in `to_canonical()` is invisible to the hash, so two
    genuinely different specs collide on one `mapper_spec_id`. Walking
    `dataclasses.fields` catches that at authoring time rather than waiting for
    a human to grep.

    Built against the most-populated fixture spec so that omit-when-default
    serialization — which optional fields added later must use, to avoid moving
    every pin — cannot hide a field from this check.
    """
    # MAXIMALLY POPULATED, and built here rather than loaded from a fixture.
    #
    # Optional fields serialize omit-when-default so that adding one does not
    # move every existing spec hash — which means a probe that leaves them empty
    # makes a correctly-handled optional field look like a forgotten one. A
    # fixture cannot be relied on to populate them: the first attempt probed
    # fixture 08, which has only two numeric fields, so the cross-field check it
    # was meant to exercise was silently skipped and the check failed anyway.
    #
    # This spec's job is to have EVERY optional field set. When a new one is
    # added, set it here too; the check failing is the reminder.
    probe = MapperSpec.from_dict(
        {
            "instruction": "probe",
            "target_fields": [
                {"name": "a", "value_type": "float", "required": True},
                {"name": "b", "value_type": "float", "required": True},
                {"name": "c", "value_type": "float", "required": True},
            ],
            "grain": {
                "identity_fields": ["k"],
                "canonical_sort": ["k"],
                "duplicate_policy": "reject",
                "source_locators": [],
                "identity_bearing_inputs": ["k"],
            },
            "cardinality": {"min_rows": 1, "max_rows": 1, "expected_per_input": 1},
            "thresholds": {
                "max_degrade_share": 0.0,
                "max_error_rate": 0.0,
                "max_unverified_share": 0.0,
                "max_absent_share": 0.0,
                "max_validation_retries": 2,
            },
            "input_adapter": "landed_text",
            "model": "claude-opus-5",
            "effort": "medium",
            "accepts_media": ["application/pdf"],
            "cross_field_checks": [{"kind": "product_equals", "target": "a", "operands": ["b", "c"]}],
            "corroboration_model": "claude-sonnet-5",
            # Legal here only because `accepts_media` above is a DOCUMENT type;
            # `citations` on an image spec is refused at construction.
            "evidence_mode": "citations",
        }
    )
    probe = _stamp_harness_version(probe.with_wire_schema(compile_schema(probe)))
    canonical_keys = set(probe.to_canonical())
    declared = {f.name for f in dc_fields(MapperSpec)}

    problems: list[str] = []
    for name in sorted(declared - canonical_keys - _HASH_EXCLUDED):
        problems.append(
            f"MapperSpec.{name} is neither in to_canonical() nor in "
            f"_HASH_EXCLUDED — decide which, or two different specs will "
            f"collide on one mapper_spec_id"
        )
    for name in sorted(canonical_keys - declared):
        problems.append(f"to_canonical() emits {name!r}, which is not a MapperSpec field")
    for name in sorted(_HASH_EXCLUDED & canonical_keys):
        problems.append(
            f"MapperSpec.{name} is in _HASH_EXCLUDED but to_canonical() emits it anyway — the exclusion list is lying"
        )
    return problems


def _check_systemic_codes() -> list[str]:
    """The gate's block set still matches the `SystemicError` hierarchy.

    `SYSTEMIC_ERROR_CODES` is walked from the class tree, so it self-heals when
    a systemic error is added — but only while the walk itself is correct. This
    pins the OUTCOME, so a refactor that breaks the derivation (a systemic class
    moved out from under `SystemicError`, an `error_code` dropped) is caught
    here rather than by a partial run landing green in production.

    The bug it guards against shipped: the gate carried its own literal set of
    three codes while five other systemic failures — including `cancelled` and
    `budget_exceeded` — landed as complete runs.
    """
    from .errors import ERROR_CODES
    from .errors import SYSTEMIC_ERROR_CODES

    #: Pinned deliberately. `coverage_blocked` is systemic in the hierarchy but
    #: excluded from the gate's inputs — it is what the gate RAISES, and feeding
    #: it back would make the decision self-referential.
    want = {
        "budget_exceeded",
        "cancelled",
        "credential_missing",
        "dependency_missing",
        "grant_missing",
        "model_not_found",
        "schema_reject",
        "spec_invalid",
    }

    problems: list[str] = []
    missing = want - SYSTEMIC_ERROR_CODES
    extra = SYSTEMIC_ERROR_CODES - want
    if missing:
        problems.append(
            f"systemic code(s) {sorted(missing)} no longer reach the gate — a "
            f"run failing this way would land as if it had completed"
        )
    if extra:
        problems.append(
            f"systemic code(s) {sorted(extra)} newly block; if that is "
            f"intended, add them to the pin in _check_systemic_codes"
        )
    unknown = SYSTEMIC_ERROR_CODES - ERROR_CODES
    if unknown:
        problems.append(
            f"systemic code(s) {sorted(unknown)} are not in ERROR_CODES, so "
            f"they cannot legally land in the error_code column"
        )
    return problems


def _check_trailing_json_parser() -> list[str]:
    """The citations path's JSON recovery still handles every known shape.

    `evidence_mode: "citations"` cannot use `output_config.format` (sending both
    is a 400), so the schema is asked for in prose and the answer arrives
    wrapped in narrative. `_trailing_json_object` recovers it. A break here does
    not look like a parser bug from the outside — every citations response
    becomes a SCHEMA_REJECT and the run reports a model that stopped complying,
    which is the wrong diagnosis entirely.

    The fixture suite cannot catch this: replay feeds `recorded.json` through
    the player, which never exercises the text path at all.

    Each case below is a shape observed or provoked on the live path, not a
    hypothetical: fenced output, a schema echoed in the preamble before the real
    answer, and a brace inside a quoted contract clause.
    """
    import json as _json

    from .transport import _trailing_json_object

    cases: list[tuple[str, str, Any]] = [
        ("bare object", '{"a": 1}', {"a": 1}),
        ("markdown fence", 'Reading:\n\n```json\n{"a": 2}\n```', {"a": 2}),
        (
            "brace inside a quoted clause",
            'The clause reads "pay {x} days".\n{"a": 3}',
            {"a": 3},
        ),
        (
            "schema echoed before the answer",
            'Schema: {"a": {"type": "int"}}\nAnswer:\n{"a": 4}',
            {"a": 4},
        ),
        ("escaped quote in a string", '{"q": "he said \\"hi\\" {"}', {"q": 'he said "hi" {'}),
    ]

    problems: list[str] = []
    for label, text, want in cases:
        try:
            got = _trailing_json_object(text)
        except _json.JSONDecodeError as exc:
            problems.append(f"{label}: raised at char {exc.pos}, expected {want!r}")
            continue
        if got != want:
            problems.append(f"{label}: got {got!r}, expected {want!r}")

    # Nothing parseable must RAISE rather than return a quiet empty dict: an
    # empty answer would land as `evidence_absent` and read as a finding about
    # the document instead of a failure to parse the response.
    try:
        _trailing_json_object("no json here at all")
        problems.append("unparseable text returned a value instead of raising")
    except _json.JSONDecodeError:
        pass

    return problems


def _bind_spec(path: Path) -> MapperSpec:
    """Load a spec.json and bind it exactly the way a run will.

    The binding sequence is the load-bearing part, not the load. `Fixture.load`
    compiles the wire schema into the spec and stamps `harness_version` BEFORE
    reading `mapper_spec_id`, because that is the hash `map_inputs` re-derives
    at the gate (CONTRACT.md §5 step 3). A hash taken from the unbound spec is a
    different 32-hex string that binds nothing — it would produce a grant that
    passes an offline check and is then refused at run time, which is the worst
    of both. This helper exists so the two CLI subcommands below and
    `Fixture.load` cannot drift on that sequence.
    """
    spec = MapperSpec.load(path)
    bound = spec.with_wire_schema(compile_schema(spec))
    if not bound.harness_version:
        bound = _stamp_harness_version(bound)
    return bound


def cmd_spec_id(spec_path: Path) -> int:
    """Print the bound `mapper_spec_id` for one spec.json, as JSON.

    The oracle a consent gate needs: "what id must a grant carry to authorize
    this spec?" JSON rather than a bare hash because the caller also needs the
    model names to explain a mismatch, and a machine reading one line of stdout
    should not have to guess whether an error arrived on it.
    """
    bound = _bind_spec(spec_path)
    print(
        json.dumps(
            {
                "mapper_spec_id": bound.mapper_spec_id,
                "model": bound.model,
                "corroboration_model": bound.corroboration_model,
                "harness_version": bound.harness_version,
            },
            sort_keys=True,
        )
    )
    return EXIT_OK


#: How `grant-check` classifies what `Grant.check` reports.
#
# `Grant.check` raises ONE `GrantError` listing every problem at once — good for
# a human fixing a grant, unusable for a caller that must file a distinct
# diagnostic code per failure kind. Rather than re-implement the rules here (two
# copies of a consent rule is how a gate ends up enforcing something other than
# what it claims), this maps the message text back onto kinds. The coupling to
# `grant.py`'s wording is real, and nothing in this package pins it — `pins`
# covers spec-id stability, canonical-form coverage and the systemic-error gate,
# not this mapping. What actually exercises three of the four kinds are the
# generate-dp eval tests (expired, model-mismatch and wrong-hash paths through
# the consent gate); "corroboration model mismatch" is pinned by nothing. A
# reworded problem that stops matching degrades to the generic `invalid` kind,
# never to silence.
_GRANT_PROBLEM_KINDS = (
    ("spec hash mismatch", "spec_mismatch"),
    ("corroboration model mismatch", "corroboration_mismatch"),
    ("model mismatch", "model_mismatch"),
    ("grant expired", "expired"),
)


def cmd_grant_check(spec_path: Path, grant_path: Path) -> int:
    """Check a grant against a spec, statically, and report as JSON.

    No runtime arguments are passed to `Grant.check`: `input_fields` and
    `document_classes` are properties of a RUN, not of a closure sitting on
    disk, so an offline caller can only exercise the statically decidable
    subset — hash, model, corroboration model, expiry. That is a real limit and
    the caller must say so; it is not a bug to be papered over by inventing
    inputs.

    Exit is always 0 when the check RAN. A non-zero exit would conflate "the
    grant does not authorize this spec" (a verdict) with "this could not be
    checked" (no verdict), and the caller needs to tell those apart.
    """
    try:
        bound = _bind_spec(spec_path)
        raw = json.loads(grant_path.read_text(encoding="utf-8"))
        # `"<derived>"` is the samples-only escape hatch (see `Fixture.load`).
        # It is NOT substituted here: a closure whose grant says `<derived>`
        # authorizes whatever spec it is handed, which is the absence of a
        # binding. Let it flow through as the literal it is and fail the hash.
        grant = Grant.from_dict(raw)
    except (OSError, json.JSONDecodeError, FieldMapperError) as exc:
        print(
            json.dumps(
                {
                    "ok": False,
                    "problems": [{"kind": "invalid", "message": str(exc)}],
                },
                sort_keys=True,
            )
        )
        return EXIT_OK

    try:
        grant.check(bound)
    except GrantError as exc:
        problems: list[dict[str, str]] = []
        for line in str(exc).splitlines():
            line = line.strip().lstrip("- ").strip()
            if not line or line.startswith("consent grant does not authorize"):
                continue
            kind = next(
                (k for prefix, k in _GRANT_PROBLEM_KINDS if line.startswith(prefix)),
                "invalid",
            )
            problems.append({"kind": kind, "message": line})
        if not problems:
            problems = [{"kind": "invalid", "message": str(exc)}]
        print(json.dumps({"ok": False, "problems": problems}, sort_keys=True))
        return EXIT_OK

    print(
        json.dumps(
            {"ok": True, "problems": [], "mapper_spec_id": bound.mapper_spec_id},
            sort_keys=True,
        )
    )
    return EXIT_OK


def cmd_pins(root: Path, args: argparse.Namespace) -> int:
    """Check spec-hash stability and canonical-form coverage.

    Two checks the fixture suite structurally cannot express: it compares
    *behaviour* against `expect.json`, and a silently-changed hash does not
    change behaviour until some grant or review fails to bind — by which point
    the cause is long gone.
    """
    problems = _check_canonical_coverage()
    for problem in problems:
        print(f"  FAIL coverage: {problem}")
    if not problems:
        print("  ok   coverage: every MapperSpec field is hashed or excluded")

    parser_problems = _check_trailing_json_parser()
    for problem in parser_problems:
        print(f"  FAIL parser: {problem}")
    if not parser_problems:
        print("  ok   parser: prose-wrapped JSON recovers on every known shape")
    problems.extend(parser_problems)

    systemic_problems = _check_systemic_codes()
    for problem in systemic_problems:
        print(f"  FAIL systemic: {problem}")
    if not systemic_problems:
        print("  ok   systemic: every SystemicError code blocks at the gate")
    problems.extend(systemic_problems)

    fixtures = sorted(p for p in root.iterdir() if p.is_dir() and (p / SPEC_FILE).exists())
    observed: dict[str, str] = {}
    for path in fixtures:
        try:
            observed[path.name] = Fixture.load(path).spec.mapper_spec_id
        except FieldMapperError as exc:
            problems.append(f"{path.name}: failed to load — {exc}")
            print(f"  FAIL {path.name}: {exc}")

    if not _SPEC_ID_PINS:
        # First run prints the pins for pasting. Deliberately NOT self-writing:
        # a check that maintains its own expectations is not a check.
        print("\n  no pins recorded yet; paste into _SPEC_ID_PINS:\n")
        for name, spec_id in sorted(observed.items()):
            print(f'    "{name}": "{spec_id}",')
        return EXIT_USAGE

    for name, spec_id in sorted(observed.items()):
        pinned = _SPEC_ID_PINS.get(name)
        if pinned is None:
            problems.append(f"{name}: no pin recorded")
            print(f"  FAIL {name}: no pin recorded (observed {spec_id})")
        elif pinned != spec_id:
            problems.append(f"{name}: hash moved")
            print(f"  FAIL {name}: pinned {pinned}, observed {spec_id}")
            print("         a moved hash unbinds every grant and invalidates every review bound to this spec.")
            print("         intended? update the pin IN THIS COMMIT with the reason. not intended? this is the bug.")
        else:
            print(f"  ok   {name}  {spec_id}")

    for name in sorted(set(_SPEC_ID_PINS) - set(observed)):
        problems.append(f"{name}: pinned but no such fixture")
        print(f"  FAIL {name}: pinned but no such fixture — stale pin")

    # `spec-id` is the oracle an external consent gate calls to learn which hash
    # a grant must carry. It reaches the hash through `_bind_spec` rather than
    # `Fixture.load`, so the two binding paths can silently diverge — and the
    # symptom would be a grant that passes the offline gate and is then refused
    # by `map_inputs` at run time, with both sides reporting confidently. Pin
    # the agreement rather than trusting that the shared helper stays shared.
    for path in fixtures:
        if path.name not in observed:
            continue
        standalone = _bind_spec(path / SPEC_FILE).mapper_spec_id
        if standalone != observed[path.name]:
            problems.append(f"{path.name}: spec-id disagrees with Fixture.load")
            print(
                f"  FAIL {path.name}: `spec-id` derives {standalone}, "
                f"Fixture.load derives {observed[path.name]} — a grant authored "
                f"against the CLI would be refused at the run gate"
            )
    if not problems:
        print("  ok   spec-id: the CLI oracle agrees with the run-gate binding")

    print()
    if problems:
        print(f"  {len(problems)} pin/coverage problem(s)")
        return EXIT_BLOCKED
    print(f"  {len(observed)} spec hash(es) stable, canonical coverage complete")
    return EXIT_OK


def cmd_verify(root: Path, args: argparse.Namespace) -> int:
    """Run every fixture and check it against its declared expectation.

    This is the acceptance suite. A fixture that asserts a block and does not
    block is a FAILURE, which is what keeps the adversarial cases honest: if the
    injected-instruction document ever starts producing a clean `ok` cell, this
    goes red rather than printing a satisfied summary.
    """
    fixtures = sorted(p for p in root.iterdir() if p.is_dir() and (p / SPEC_FILE).exists())
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
            # A separate answer table, so the two readers' responses are
            # visibly distinct in the fixture rather than interleaved in one
            # file. None when the fixture declares no corroboration, which
            # `map_inputs` refuses if the spec asked for it.
            corroborate=(RecordedPlayer(fixture.corroborated) if fixture.corroborated else None),
        )
    except GrantError as exc:
        if expect.get("grant_refused"):
            return None
        return f"grant refused unexpectedly: {exc}"
    except SystemicError as exc:
        if expect.get("blocks"):
            # A fixture may pin WHICH block it expects. `blocks: true` alone
            # passes on any systemic failure, so a fixture asserting a specific
            # refusal would still go green if an unrelated error replaced it —
            # the fixture would look like it still proved something it no
            # longer tests.
            want_code = expect.get("blocks_error_code")
            if want_code and exc.error_code != want_code:
                return f"blocked with [{exc.error_code}], expected [{want_code}]: {exc}"
            want_text = expect.get("blocks_message_contains")
            if want_text and want_text not in str(exc):
                return f"block message did not contain {want_text!r}: {exc}"
            return None
        return f"systemic failure: [{exc.error_code}] {exc}"

    if expect.get("grant_refused"):
        return "expected the grant to be refused, but the run proceeded"

    # Quarantine expectations.
    quarantined = {q.input_id for q in result.quarantined}
    want_quarantined = set(expect.get("quarantined", []))
    if quarantined != want_quarantined:
        return f"quarantined {sorted(quarantined)}, expected {sorted(want_quarantined)}"

    # Status-count expectations.
    counts = result.status_counts()
    status_counts: Mapping[str, int] = cast(Mapping[str, int], expect.get("status_counts") or {})
    for status, want in status_counts.items():
        if counts.get(status, 0) != want:
            return f"status {status}: got {counts.get(status, 0)}, expected {want}"

    # Evidence verify_status expectations.
    ev_counts: dict[str, int] = {}
    for atom in result.evidence:
        ev_counts[atom.verify_status.value] = ev_counts.get(atom.verify_status.value, 0) + 1
    evidence_counts: Mapping[str, int] = cast(Mapping[str, int], expect.get("evidence_counts") or {})
    for status, want in evidence_counts.items():
        if ev_counts.get(status, 0) != want:
            return f"evidence {status}: got {ev_counts.get(status, 0)}, expected {want}"

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
                return f"{proposal.field}: value {proposal.typed.value!r}, expected {want_cell['value']!r}"
        if "value_not" in want_cell and proposal.typed.value == want_cell["value_not"]:
            return f"{proposal.field}: landed the forbidden value {want_cell['value_not']!r} — the attack succeeded"

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
        min_evidence_per_ok_cell={f.name: f.min_evidence for f in fixture.spec.target_fields},
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
        return f"expected blocks={expect['blocks']}, got blocked={blocked}" + (
            f" ({'; '.join(report.reasons)})" if report.reasons else ""
        )

    # A4: which cells carry unfalsifiable evidence. Declared per fixture so the
    # media-direct path cannot silently start looking checkable — the whole
    # point of the column is that `ok` alone does not distinguish the two.
    if "unfalsifiable_cells" in expect:
        marked = sorted(c.field for c in resolution.effective if c.evidence_unfalsifiable)
        want_marked = sorted(expect["unfalsifiable_cells"])
        if marked != want_marked:
            return f"unfalsifiable cells {marked}, expected {want_marked}"

    # -- resolve round trip ------------------------------------------------
    # Land the long form to CSV, read it back, and re-resolve. `resolve` is a
    # SEPARATE step in real use — a reviewer edits reviews.csv days later and
    # re-runs it against landed records, with no model call — so the records
    # must survive the trip through CSV without changing meaning.
    #
    # The failure this catches is quiet: a value that comes back as the string
    # "90.0" instead of the float 90.0 hashes differently, so every review bound
    # to that cell goes stale for a reason no human could see. Comparing the
    # re-resolved wide rows against the in-memory ones makes that loud.
    landed_proposals = proposals_from_csv(
        rows_to_csv([p.as_row() for p in result.proposals], PROPOSAL_COLUMNS),
        evidence_from_csv(rows_to_csv([e.as_row() for e in result.evidence], EVIDENCE_COLUMNS)),
    )
    reresolved = resolve(
        landed_proposals,
        bind_reviews_to_landed(fixture.reviews, landed_proposals, fixture),
        evidence_from_csv(rows_to_csv([e.as_row() for e in result.evidence], EVIDENCE_COLUMNS)),
        fields=list(fixture.spec.field_names),
        row_keys=result.row_keys,
        min_evidence_per_ok_cell={f.name: f.min_evidence for f in fixture.spec.target_fields},
    )
    if reresolved.wide_rows != resolution.wide_rows:
        return (
            "resolve round trip changed the wide projection: landing the long "
            "form and re-resolving it produced different rows, so a review "
            "cycle would not see what the run landed"
        )
    # PROVENANCE, not just the wide rows. The wide projection compares values
    # with Python equality, where 90 == 90.0 and True == 1, so it is blind to
    # exactly the round-trip defects that matter — a float cell landing as an
    # int hashes differently and silently stales every review bound to it while
    # both sides still display "90". The sidecar carries value_hash,
    # value_status, needs_review, effective_source and reviewer, which is where
    # that shows up.
    if reresolved.provenance != resolution.provenance:
        before = {(r["target_row_key"], r["field"]): r for r in resolution.provenance}
        diffs = [
            f"{row['field']}: {before.get((row['target_row_key'], row['field']))} -> {row}"
            for row in reresolved.provenance
            if before.get((row["target_row_key"], row["field"])) != row
        ]
        return "resolve round trip changed the provenance sidecar: " + (diffs[0] if diffs else "row set differs")
    # Stale review IDENTITY, not just the count. A swap — one review going
    # stale in place of another — keeps the count and changes who has to
    # re-review.
    if reresolved.stale_review_rows != resolution.stale_review_rows:
        return (
            f"resolve round trip changed which reviews went stale: "
            f"{resolution.stale_review_rows} in-memory, "
            f"{reresolved.stale_review_rows} after the CSV trip"
        )
    return None


# ==========================================================================
# Entry point
# ==========================================================================


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m nxd.experimental.field_mapper",
        description=(
            "Run one mapper spec over sample inputs; print long-form rows, the "
            "wide projection, and issue counts by value_status."
        ),
    )
    parser.add_argument(
        "command",
        choices=(
            "preflight",
            "canary",
            "run",
            "resolve",
            "verify",
            "pins",
            "spec-id",
            "grant-check",
        ),
    )
    parser.add_argument(
        "target",
        nargs="?",
        help=(
            "fixture directory (or the samples root, for `verify`; a spec.json path for `spec-id` and `grant-check`)"
        ),
    )
    parser.add_argument(
        "grant",
        nargs="?",
        help="grant.json path — `grant-check` only",
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
        "--provider",
        choices=PROVIDER_KINDS,
        default="anthropic",
        help=(
            "where the call goes. 'anthropic' is the contract of record. "
            "'claude_cli' shells out to the local `claude -p` binary: cheap, no "
            "API key, but NOT equivalent — no schema enforcement, media arrives "
            "via a filesystem read rather than a content block, and it is an "
            "agent loop rather than one call. A response captured under it is "
            "not a valid recorded.json for the Anthropic path."
        ),
    )
    parser.add_argument(
        "--provider-model",
        default=None,
        metavar="NAME",
        help=(
            "model override for the selected provider, e.g. 'sonnet' for "
            "claude_cli. Ignored by the anthropic provider, which takes its "
            "model from the spec so the call and mapper_spec_id agree."
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
    # The acceptance fixtures ship inside the package, so `verify` and `pins`
    # answer "is this harness intact?" from any install, not only from a repo
    # checkout. Resolved in two places because this file has two homes: beside
    # this module in the installed package, and one level up in the skill repo
    # that is its source of truth. Checking both keeps the two copies
    # byte-identical, so neither can quietly drift from the other.
    default_root = next(
        (p for p in (Path(__file__).parent / "samples", Path(__file__).parent.parent / "samples") if p.is_dir()),
        Path(__file__).parent / "samples",
    )
    target = Path(args.target) if args.target else default_root

    try:
        if args.command in ("verify", "pins"):
            # A NAMED target that is not a directory is a usage error, never a
            # silent fall back to the packaged fixtures. These two commands
            # exist to answer "is this harness intact?", so verifying something
            # other than what the caller named — and printing 13/13 for it —
            # is the one wrong answer they must not give. Omitting the target
            # still defaults to the packaged samples, which is what makes the
            # bare invocation work from any install.
            if args.target and not target.is_dir():
                print(f"not a fixture directory: {target}", file=sys.stderr)
                return EXIT_USAGE
            return cmd_verify(target, args) if args.command == "verify" else cmd_pins(target, args)
        # `spec-id` and `grant-check` take FILE paths, not a fixture directory,
        # and deliberately do not go through `Fixture.load`: a closure carries a
        # spec and a grant under contracts/ with no inputs.json, no recorded.json
        # and no expect.json, so requiring a fixture would make the consent
        # oracle unusable on the only artifacts a closure actually has.
        if args.command == "spec-id":
            if not args.target:
                print("spec-id needs a spec.json path", file=sys.stderr)
                return EXIT_USAGE
            return cmd_spec_id(Path(args.target))
        if args.command == "grant-check":
            if not args.target or not args.grant:
                print(
                    "grant-check needs a spec.json and a grant.json path",
                    file=sys.stderr,
                )
                return EXIT_USAGE
            return cmd_grant_check(Path(args.target), Path(args.grant))

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

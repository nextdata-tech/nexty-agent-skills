"""The mapper spec: canonicalization and `mapper_spec_id`. CONTRACT.md §5, design §12.

The spec is **data, not code**. Design §12 is explicit: the instruction text *is*
the rubric, and a dict literal in `transform/main.py` is policy as a transform
literal — the defect `derivation-plan.md` names. The spec is landed (a reference
model or `contracts/<name>.md` + an `nxd_decisions` row) and loaded here; the
transform keeps only wiring.

Two invariants this module exists to protect:

1. **A spec that cannot declare stable row identity is REJECTED at construction**
   (design §3). Not warned about, not defaulted to an ordinal — rejected, before
   any source is read and before any credential is touched. An ordinal key
   silently reattaches every human review to the wrong row on a source reorder,
   and the uniqueness assert does not catch it.

2. **`mapper_spec_id` is a hash of semantics only** (CONTRACT.md §5). The
   exclusion list is a contract, not an optimization: if a filesystem path leaked
   into the hash, the id would change when the closure moved directory and every
   human review in the dataset would auto-invalidate at once.

Layer 2 lives in the *contents* of a spec — prompt text, field grouping,
evidence granularity. This module is Layer 1: the shape those contents must take
and the hash that versions them.

Pure stdlib. No network.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field as dc_field
from pathlib import Path
from typing import Any, Final, Mapping, Sequence

from .errors import SpecError
from .identity import canonical_json, digest, full_digest
from .media import SUPPORTED_MEDIA_TYPES

__all__ = [
    "VALUE_TYPES",
    "DUPLICATE_POLICIES",
    "INPUT_ADAPTER_KINDS",
    "TargetField",
    "GrainDeclaration",
    "Cardinality",
    "Thresholds",
    "MapperSpec",
]

#: The five typed value slots of `mapper_proposals` (CONTRACT.md §2.1). Five
#: nullable columns rather than one string column: a single string satisfies the
#: letter of "never a string sentinel in a numeric column" (there is no numeric
#: column) and defeats its purpose — every consumer casts, and a bad cast becomes
#: a query-time error instead of a build-time one.
VALUE_TYPES: Final[frozenset[str]] = frozenset(
    {"string", "int", "float", "bool", "timestamp"}
)

#: CONTRACT.md §5. `ordinal_suffix` is supported but carries an explicit warning:
#: review binding is fragile under it, because reordering the source changes the
#: key. Open question 8 asks whether it should be a documented trap instead.
DUPLICATE_POLICIES: Final[frozenset[str]] = frozenset(
    {"reject", "ordinal_suffix", "merge_by_rule"}
)

#: How inputs reach the model. Layer 2 chooses; Layer 1 fixes the closed set so
#: the choice is hashed into `mapper_spec_id` and visible in an experiment diff.
INPUT_ADAPTER_KINDS: Final[frozenset[str]] = frozenset(
    {"landed_rows", "landed_text", "document_blob"}
)


@dataclass(frozen=True)
class TargetField:
    """One field the mapper produces, with the constraints that govern it.

    The `enforced_by` split is the point of this class. CONTRACT.md §8: the wire
    JSON Schema supports `type`, `enum`, `const`, `anyOf`, `$ref`, and string
    `format` — it supports **neither** `minimum`/`maximum` nor
    `minLength`/`maxLength`. So every constraint declared here routes to one of
    two enforcement points, and the routing is where the "we thought the API
    enforced it" bug lives. Recording the route on the field makes it explicit
    and testable offline.
    """

    name: str
    value_type: str
    #: Closed value set -> wire schema `enum`. The API enforces this one.
    enum: tuple[Any, ...] | None = None
    #: Numeric range -> `validate.py`. The API CANNOT enforce it. This is where
    #: retry earns its place: a range violation is a recoverable model error, so
    #: re-asking with the violation named is a legitimate bounded correction.
    minimum: float | None = None
    maximum: float | None = None
    #: String length -> `validate.py`, same reasoning.
    min_length: int | None = None
    max_length: int | None = None
    #: Whether the model must return this field -> wire schema `required`.
    required: bool = True
    #: Minimum evidence atoms for an `ok` cell (CONTRACT.md §7 assert 2).
    min_evidence: int = 1
    description: str = ""

    def __post_init__(self) -> None:
        if not self.name or not self.name.strip():
            raise SpecError("target field name must be a non-empty string")
        if self.value_type not in VALUE_TYPES:
            raise SpecError(
                f"target field {self.name!r} has unknown value_type "
                f"{self.value_type!r}; expected one of {sorted(VALUE_TYPES)}"
            )
        if self.minimum is not None and self.maximum is not None:
            if self.minimum > self.maximum:
                raise SpecError(
                    f"target field {self.name!r}: minimum {self.minimum} exceeds "
                    f"maximum {self.maximum}"
                )
        if self.min_length is not None and self.max_length is not None:
            if self.min_length > self.max_length:
                raise SpecError(
                    f"target field {self.name!r}: min_length {self.min_length} "
                    f"exceeds max_length {self.max_length}"
                )
        if (self.minimum is not None or self.maximum is not None) and self.value_type not in {
            "int",
            "float",
        }:
            raise SpecError(
                f"target field {self.name!r}: numeric range declared on a "
                f"{self.value_type} field. The range would never be checked."
            )
        if (self.min_length is not None or self.max_length is not None) and (
            self.value_type != "string"
        ):
            raise SpecError(
                f"target field {self.name!r}: length constraint declared on a "
                f"{self.value_type} field. The constraint would never be checked."
            )
        if self.min_evidence < 0:
            raise SpecError(f"target field {self.name!r}: min_evidence cannot be negative")
        if self.enum is not None and len(self.enum) == 0:
            raise SpecError(
                f"target field {self.name!r}: empty enum makes every value invalid"
            )

    @property
    def harness_enforced_constraints(self) -> tuple[str, ...]:
        """Constraints `validate.py` owns because the wire schema cannot express them.

        CONTRACT.md §8's routing table, computed rather than restated, so a new
        constraint kind cannot be added to this class without landing here.
        """
        owned: list[str] = []
        if self.minimum is not None:
            owned.append("minimum")
        if self.maximum is not None:
            owned.append("maximum")
        if self.min_length is not None:
            owned.append("min_length")
        if self.max_length is not None:
            owned.append("max_length")
        if self.min_evidence > 0:
            owned.append("evidence_substring")
        return tuple(owned)

    def to_canonical(self) -> dict[str, Any]:
        """Semantic projection for the spec hash. `description` is excluded.

        CONTRACT.md §5 step 4 excludes "any comment or description field
        explicitly marked non-semantic." A description edit is documentation, and
        making it invalidate every human review bound to this spec would train
        reviewers to never improve a description.
        """
        return {
            "name": self.name,
            "value_type": self.value_type,
            "enum": list(self.enum) if self.enum is not None else None,
            "minimum": self.minimum,
            "maximum": self.maximum,
            "min_length": self.min_length,
            "max_length": self.max_length,
            "required": self.required,
            "min_evidence": self.min_evidence,
        }


@dataclass(frozen=True)
class GrainDeclaration:
    """What makes a target row a row. Design §3 — the axis the design got wrong.

    Every element here is mandatory in spirit; `identity_fields` is mandatory in
    code. This is the declaration whose absence causes construction to fail.
    """

    #: Which input fields determine a target row. Order is significant: it fixes
    #: the digest input order in `identity.target_row_key`, so the key cannot
    #: shift because a dict iterated differently.
    identity_fields: tuple[str, ...]
    #: Canonical sort order for `input_snapshot_id`. Without it, an input
    #: reorder changes the snapshot id and mass-invalidates every review for a
    #: no-op source change.
    canonical_sort: tuple[str, ...]
    #: What to do when two target rows derive the same key.
    duplicate_policy: str = "reject"
    #: Stable source locators for when identity fields alone are insufficient —
    #: two employment records at the same employer, per CONTRACT.md §5.
    source_locators: tuple[str, ...] = ()
    #: Which input fields are identity-bearing for `input_snapshot_id`. Defaults
    #: to `identity_fields`. Scoping this narrowly is deliberate: a change to a
    #: field the spec does not read must NOT throw away the reviewer's work.
    identity_bearing_inputs: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        # THE rejection. Design §3: a spec that cannot define stable row identity
        # is rejected — before any source read, before any credential is touched.
        if not self.identity_fields:
            raise SpecError(
                "mapper spec declares no identity_fields, so target rows would have "
                "no stable identity and reviews would bind to emission position. "
                "Design §3: an emission ordinal is not a valid key — reversing the "
                "source silently reattaches every review to a different row while "
                "the uniqueness assert still passes. Declare identity_fields (and "
                "source_locators where the identity fields alone cannot separate "
                "two rows)."
            )
        if len(set(self.identity_fields)) != len(self.identity_fields):
            raise SpecError(
                f"identity_fields contains duplicates: {list(self.identity_fields)!r}"
            )
        if self.duplicate_policy not in DUPLICATE_POLICIES:
            raise SpecError(
                f"unknown duplicate_policy {self.duplicate_policy!r}; "
                f"expected one of {sorted(DUPLICATE_POLICIES)}"
            )
        if not self.canonical_sort:
            raise SpecError(
                "mapper spec declares no canonical_sort. `input_snapshot_id` would "
                "then depend on the order rows happened to arrive in, so an input "
                "reorder would invalidate every human review for a no-op change."
            )
        bearing = self.identity_bearing_inputs or self.identity_fields
        unknown_sort = [f for f in self.canonical_sort if f not in bearing]
        if unknown_sort:
            raise SpecError(
                f"canonical_sort references field(s) {unknown_sort!r} that are not "
                "identity-bearing; the sort must be computable from the hashed "
                "projection or the snapshot id is not reproducible"
            )

    @property
    def effective_identity_bearing_inputs(self) -> tuple[str, ...]:
        """Identity-bearing inputs, defaulting to the identity fields."""
        return self.identity_bearing_inputs or self.identity_fields

    def to_canonical(self) -> dict[str, Any]:
        """Semantic projection. Every field here is semantic — none is excluded."""
        return {
            "identity_fields": list(self.identity_fields),
            "canonical_sort": list(self.canonical_sort),
            "duplicate_policy": self.duplicate_policy,
            "source_locators": list(self.source_locators),
            "identity_bearing_inputs": list(self.effective_identity_bearing_inputs),
        }


@dataclass(frozen=True)
class Cardinality:
    """Declared N->M shape. NEVER inferred from input count (design §1).

    CONTRACT.md §7 assert 4 checks the emitted row count against these bounds,
    and explicitly forbids a Tier-1 "output count == source count" assert — that
    assert is unsatisfiable for N->M and is the one `derived-models.md` will need
    amending for.
    """

    min_rows: int
    max_rows: int | None = None
    #: Expected rows per input, for the per-input shape check. `None` = unbounded.
    expected_per_input: float | None = None

    def __post_init__(self) -> None:
        if self.min_rows < 0:
            raise SpecError("cardinality min_rows cannot be negative")
        if self.max_rows is not None and self.max_rows < self.min_rows:
            raise SpecError(
                f"cardinality max_rows {self.max_rows} is below min_rows {self.min_rows}"
            )

    def to_canonical(self) -> dict[str, Any]:
        return {
            "min_rows": self.min_rows,
            "max_rows": self.max_rows,
            "expected_per_input": self.expected_per_input,
        }


@dataclass(frozen=True)
class Thresholds:
    """The §4 blocking shares. **No defaults** — the spec must declare them.

    CONTRACT.md open question 1 asks for defaults and answers its own question:
    "a wrong default is worse than an absent one." A too-loose default makes §4
    decorative; a too-tight one makes every first run block. So these are
    required, and a spec author has to think about them once.

    `max_absent_share` is genuinely optional — a sparse source legitimately
    declares no ceiling — and is the only one that may be `None`.
    """

    max_degrade_share: float
    max_error_rate: float
    max_unverified_share: float
    max_absent_share: float | None = None
    #: Validation retries per cell (CONTRACT.md §8). Distinct from transport
    #: retries, which are a transport concern and never conflated with these.
    max_validation_retries: int = 2

    def __post_init__(self) -> None:
        for name in ("max_degrade_share", "max_error_rate", "max_unverified_share"):
            value = getattr(self, name)
            if value is None:
                raise SpecError(
                    f"{name} must be declared. There is no principled default: too "
                    "loose makes the blocking table decorative, too tight blocks "
                    "every first run."
                )
            if not 0.0 <= float(value) <= 1.0:
                raise SpecError(f"{name} must be a share in [0.0, 1.0], got {value!r}")
        if self.max_absent_share is not None and not 0.0 <= float(self.max_absent_share) <= 1.0:
            raise SpecError(
                f"max_absent_share must be a share in [0.0, 1.0], got {self.max_absent_share!r}"
            )
        if self.max_validation_retries < 0:
            raise SpecError("max_validation_retries cannot be negative")

    def to_canonical(self) -> dict[str, Any]:
        return {
            "max_degrade_share": self.max_degrade_share,
            "max_error_rate": self.max_error_rate,
            "max_unverified_share": self.max_unverified_share,
            "max_absent_share": self.max_absent_share,
            "max_validation_retries": self.max_validation_retries,
        }


@dataclass(frozen=True)
class MapperSpec:
    """A complete, validated mapper spec. `mapper_spec_id` versions it.

    Construction validates; there is no separate `.validate()` to forget to call.
    An invalid spec cannot exist as an object, which is what keeps an unusable
    spec from reaching the transport layer at all.
    """

    #: The rubric. Design §12: this text IS the experiment variable, which is why
    #: canonicalization normalizes line endings and trailing whitespace and
    #: performs NO other rewriting.
    instruction: str
    target_fields: tuple[TargetField, ...]
    grain: GrainDeclaration
    cardinality: Cardinality
    thresholds: Thresholds
    input_adapter: str
    model: str = "claude-opus-5"
    #: `output_config.effort` (CONTRACT.md §8). Depth is declared here; there is
    #: deliberately no `temperature`/`top_p`/`top_k` anywhere in this class —
    #: they are rejected with 400 on this model and were rejected by design
    #: review independently. Do not add them back "for determinism"; they never
    #: guaranteed it.
    effort: str = "medium"
    #: Media types this mapper accepts as non-text input, e.g.
    #: `("application/pdf",)` or `("image/png", "image/jpeg")`. Empty means
    #: text-only. Semantic, so it is hashed into `mapper_spec_id`: a mapper that
    #: starts accepting images is reading different sources and every review bound
    #: to the text-only spec should come unbound.
    accepts_media: tuple[str, ...] = ()
    spec_version: str = "1"
    #: Compiled wire-schema bytes, hashed into the spec id per §5 step 3. Set by
    #: `schema.py` after compilation; `None` until then.
    wire_schema: Mapping[str, Any] | None = None
    #: Harness version. CONTRACT.md open question 6: without it in the hash, a
    #: harness change is invisible in an experiment comparison.
    harness_version: str = ""
    #: Non-semantic. Excluded from the hash (§5 step 4).
    description: str = ""
    source_path: str | None = dc_field(default=None, compare=False)

    def __post_init__(self) -> None:
        if not self.instruction or not self.instruction.strip():
            raise SpecError(
                "mapper spec has no instruction text. The instruction is the rubric; "
                "an empty one makes every proposal unreviewable."
            )
        if not self.target_fields:
            raise SpecError("mapper spec declares no target fields")
        names = [f.name for f in self.target_fields]
        duplicates = sorted({n for n in names if names.count(n) > 1})
        if duplicates:
            raise SpecError(
                f"duplicate target field name(s) {duplicates!r}; "
                "(target_row_key, field) would not be unique"
            )
        if self.input_adapter not in INPUT_ADAPTER_KINDS:
            raise SpecError(
                f"unknown input_adapter {self.input_adapter!r}; "
                f"expected one of {sorted(INPUT_ADAPTER_KINDS)}"
            )
        if not self.model or not self.model.strip():
            raise SpecError("mapper spec must name a model")
        unsupported = [m for m in self.accepts_media if m not in SUPPORTED_MEDIA_TYPES]
        if unsupported:
            supported = ", ".join(sorted(SUPPORTED_MEDIA_TYPES))
            raise SpecError(
                f"accepts_media names unsupported media type(s) {unsupported!r}; "
                f"the API accepts {supported}. Declaring one the API rejects "
                "costs a call and returns a schema reject, so it is refused here."
            )

    # -- media -------------------------------------------------------------

    @property
    def accepts_media_input(self) -> bool:
        return bool(self.accepts_media)

    @property
    def evidence_bearing_fields(self) -> tuple[str, ...]:
        """Fields that require at least one evidence atom."""
        return tuple(f.name for f in self.target_fields if f.min_evidence > 0)

    def media_direct_report(self) -> list[str]:
        """What a media-direct run cannot verify, stated before the first call.

        A media-direct mapper — media in, no landed text — has no substring
        haystack, so `verified` is unreachable and every atom lands
        `evidence_unverified`. That is permitted: a caller asking "read this
        screenshot" is asking for exactly it, and refusing would block the case
        outright until staged extraction exists.

        What is NOT permitted is discovering it in the results. This returns the
        lines a preflight report must print. It is DERIVED from the declared
        fields rather than trusting a declaration, because the failure mode here
        is a spec that quietly sets `max_unverified_share: 1.0` and thereby makes
        §4's strongest ceiling decorative without anyone noticing.

        Empty list means nothing to warn about. Callers that hold actual inputs
        should prefer `media_direct_report_for_inputs`, which knows whether landed
        text is present rather than inferring from the spec alone.
        """
        if not self.accepts_media_input:
            return []
        bearing = self.evidence_bearing_fields
        lines = [
            f"media-direct spec: accepts {', '.join(self.accepts_media)} with no "
            "landed-text surface, so the evidence substring check cannot run"
        ]
        if bearing:
            lines.append(
                f"'verified' is UNREACHABLE for {len(bearing)} of "
                f"{len(self.target_fields)} field(s): {', '.join(bearing)}"
            )
            lines.append("every evidence atom will land 'evidence_unverified'")
            # Observed live, not theoretical: claude-haiku-4-5 read $30.00 off a
            # fixture image whose total is $90.00, cited "$30.00", and landed the
            # cell `ok` on four consecutive runs. Type, range, and evidence-count
            # checks all passed; nothing else could run. `evidence_unverified`
            # reads like "we could not check this one", which badly understates
            # it — so the preflight says the sharper thing outright.
            lines.append(
                "there is NO mechanism linking a value to its source on this "
                "path: the quote is a string the model chose about an artifact "
                "the harness cannot read, so a wrong value is indistinguishable "
                "from a right one"
            )
            lines.append(
                "model choice is therefore a CORRECTNESS decision here, not a "
                "cost one — a smaller model has no safety net on this path"
            )
        if self.thresholds.max_unverified_share < 1.0:
            lines.append(
                f"max_unverified_share is {self.thresholds.max_unverified_share} "
                "but a media-direct run produces 100% unverified atoms, so this "
                "run will BLOCK on the unverified ceiling. Either declare 1.0 and "
                "accept an evidence-blind mapper, or stage extraction so landed "
                "text exists to verify against."
            )
        return lines

    # -- lookup ------------------------------------------------------------

    @property
    def field_names(self) -> tuple[str, ...]:
        """Declared target field names, in declaration order."""
        return tuple(f.name for f in self.target_fields)

    def field(self, name: str) -> TargetField:
        """Look up a declared target field, or reject.

        `records.py` calls this to reject a proposal for an undeclared field —
        CONTRACT.md §2.1 requires `field` to be one the spec declares, and an
        undeclared field means the model invented a column.
        """
        for f in self.target_fields:
            if f.name == name:
                return f
        raise SpecError(
            f"field {name!r} is not declared by this mapper spec; "
            f"declared fields are {list(self.field_names)!r}"
        )

    # -- canonicalization and hashing --------------------------------------

    @staticmethod
    def normalize_instruction(text: str) -> str:
        """Normalize line endings and strip trailing whitespace per line. Nothing else.

        CONTRACT.md §5 step 2. The restraint is the point: the rubric text is the
        experiment variable, so it must not be silently altered. Collapsing
        internal whitespace or rewrapping would change the prompt while leaving
        `mapper_spec_id` looking like it described the original.
        """
        unified = text.replace("\r\n", "\n").replace("\r", "\n")
        return "\n".join(line.rstrip() for line in unified.split("\n"))

    def to_canonical(self) -> dict[str, Any]:
        """The semantic projection that `mapper_spec_id` hashes. CONTRACT.md §5.

        INCLUDED (§5 step 3): instruction text, target fields with types/ranges/
        enums, grain, cardinality bounds, canonical sort, duplicate policy,
        evidence requirements, thresholds, model id, wire schema bytes, and the
        harness version.

        EXCLUDED (§5 step 4): everything nondeterministic — `execution_id`,
        timestamps, file paths, the API key, and non-semantic descriptions. This
        exclusion list is a contract, not an optimization: a leaked path means
        `mapper_spec_id` changes when the closure moves directory, and every
        human review in the dataset auto-invalidates at once.
        """
        return {
            "instruction": self.normalize_instruction(self.instruction),
            "target_fields": [f.to_canonical() for f in self.target_fields],
            "grain": self.grain.to_canonical(),
            "cardinality": self.cardinality.to_canonical(),
            "thresholds": self.thresholds.to_canonical(),
            "input_adapter": self.input_adapter,
            "model": self.model,
            "effort": self.effort,
            "accepts_media": list(self.accepts_media),
            "spec_version": self.spec_version,
            "wire_schema": self.wire_schema if self.wire_schema is not None else None,
            "harness_version": self.harness_version,
        }

    def canonical_bytes(self) -> bytes:
        """UTF-8 canonical serialization — §5 step 5's hash input."""
        return canonical_json(self.to_canonical()).encode("utf-8")

    @property
    def mapper_spec_id(self) -> str:
        """`sha256` over the canonicalized spec, at landed column width.

        Binds reviews (§2.2) and keys the server-side schema cache (§1). A change
        to any *semantic* element auto-invalidates every review bound to the old
        id — which is the intent: a changed rubric means the old approval was for
        a different question.
        """
        return digest(self.canonical_bytes())

    @property
    def mapper_spec_id_full(self) -> str:
        """Full 64-char digest, for the ledger."""
        return full_digest(self.canonical_bytes())

    # -- loading -----------------------------------------------------------

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> "MapperSpec":
        """Build from a plain mapping (the landed spec's JSON form).

        Unknown top-level keys are rejected rather than ignored. A typo'd key
        that silently does nothing is how a spec ends up not declaring the
        threshold its author believed they declared.
        """
        known = {
            "instruction",
            "target_fields",
            "grain",
            "cardinality",
            "thresholds",
            "input_adapter",
            "model",
            "effort",
            "accepts_media",
            "spec_version",
            "wire_schema",
            "harness_version",
            "description",
        }
        unknown = sorted(set(raw) - known)
        if unknown:
            raise SpecError(
                f"unknown key(s) in mapper spec: {unknown!r}. Rejected rather than "
                "ignored — a silently-dropped key is how a spec ends up not "
                "declaring what its author believed it declared."
            )
        for required_key in ("instruction", "target_fields", "grain", "cardinality",
                             "thresholds", "input_adapter"):
            if required_key not in raw:
                raise SpecError(f"mapper spec is missing required key {required_key!r}")

        grain_raw = dict(raw["grain"])
        grain = GrainDeclaration(
            identity_fields=tuple(grain_raw.get("identity_fields", ())),
            canonical_sort=tuple(grain_raw.get("canonical_sort", ())),
            duplicate_policy=grain_raw.get("duplicate_policy", "reject"),
            source_locators=tuple(grain_raw.get("source_locators", ())),
            identity_bearing_inputs=tuple(grain_raw.get("identity_bearing_inputs", ())),
        )
        card_raw = dict(raw["cardinality"])
        cardinality = Cardinality(
            min_rows=int(card_raw.get("min_rows", 0)),
            max_rows=card_raw.get("max_rows"),
            expected_per_input=card_raw.get("expected_per_input"),
        )
        thr_raw = dict(raw["thresholds"])
        thresholds = Thresholds(
            max_degrade_share=thr_raw.get("max_degrade_share"),  # type: ignore[arg-type]
            max_error_rate=thr_raw.get("max_error_rate"),  # type: ignore[arg-type]
            max_unverified_share=thr_raw.get("max_unverified_share"),  # type: ignore[arg-type]
            max_absent_share=thr_raw.get("max_absent_share"),
            max_validation_retries=int(thr_raw.get("max_validation_retries", 2)),
        )
        fields: list[TargetField] = []
        for f_raw in raw["target_fields"]:
            f_dict = dict(f_raw)
            enum_val = f_dict.get("enum")
            fields.append(
                TargetField(
                    name=f_dict.get("name", ""),
                    value_type=f_dict.get("value_type", ""),
                    enum=tuple(enum_val) if enum_val is not None else None,
                    minimum=f_dict.get("minimum"),
                    maximum=f_dict.get("maximum"),
                    min_length=f_dict.get("min_length"),
                    max_length=f_dict.get("max_length"),
                    required=bool(f_dict.get("required", True)),
                    min_evidence=int(f_dict.get("min_evidence", 1)),
                    description=f_dict.get("description", ""),
                )
            )
        return cls(
            instruction=raw["instruction"],
            target_fields=tuple(fields),
            grain=grain,
            cardinality=cardinality,
            thresholds=thresholds,
            input_adapter=raw["input_adapter"],
            model=raw.get("model", "claude-opus-5"),
            effort=raw.get("effort", "medium"),
            accepts_media=tuple(raw.get("accepts_media", ())),
            spec_version=str(raw.get("spec_version", "1")),
            wire_schema=raw.get("wire_schema"),
            harness_version=raw.get("harness_version", ""),
            description=raw.get("description", ""),
        )

    @classmethod
    def load(cls, path: str | Path) -> "MapperSpec":
        """Load a landed spec from JSON. Public per CONTRACT.md §1.

        `source_path` is recorded for diagnostics and is excluded from `compare`
        and from the canonical form — see `to_canonical`. A path in the hash
        would make `mapper_spec_id` move when the closure moves directory.
        """
        p = Path(path)
        try:
            raw = json.loads(p.read_text(encoding="utf-8"))
        except FileNotFoundError as exc:
            raise SpecError(f"mapper spec not found at {p}") from exc
        except json.JSONDecodeError as exc:
            raise SpecError(f"mapper spec at {p} is not valid JSON: {exc}") from exc
        if not isinstance(raw, dict):
            raise SpecError(f"mapper spec at {p} must be a JSON object")
        spec = cls.from_dict(raw)
        object.__setattr__(spec, "source_path", str(p))
        return spec

    def with_wire_schema(self, wire_schema: Mapping[str, Any]) -> "MapperSpec":
        """Return a copy carrying the compiled wire schema.

        Returns a NEW spec rather than mutating, because `mapper_spec_id` changes
        when the wire schema does — §5 step 3 includes the schema bytes. Mutating
        in place would let an object's id change under a caller that had already
        read it, which is the drift the frozen dataclass exists to prevent.
        """
        return MapperSpec(
            instruction=self.instruction,
            target_fields=self.target_fields,
            grain=self.grain,
            cardinality=self.cardinality,
            thresholds=self.thresholds,
            input_adapter=self.input_adapter,
            model=self.model,
            effort=self.effort,
            accepts_media=list(self.accepts_media),
            spec_version=self.spec_version,
            wire_schema=dict(wire_schema),
            harness_version=self.harness_version,
            description=self.description,
            source_path=self.source_path,
        )

    def __repr__(self) -> str:
        """Compact repr. Deliberately omits the instruction text.

        The instruction can be thousands of characters of rubric, and a repr that
        dumps it ends up in exception messages and log lines — the surfaces
        CONTRACT.md §9 requires to stay free of bulk content.
        """
        return (
            f"MapperSpec(mapper_spec_id={self.mapper_spec_id!r}, "
            f"model={self.model!r}, fields={list(self.field_names)!r}, "
            f"input_adapter={self.input_adapter!r})"
        )

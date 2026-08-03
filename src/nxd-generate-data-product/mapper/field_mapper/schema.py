"""Mapper spec -> Anthropic JSON Schema, and what that schema *cannot* express.

CONTRACT.md §8. This module exists because the hardest transport fact is a
negative one: the JSON Schema accepted by `output_config.format` supports
`type`, `enum`, `const`, `anyOf`, `$ref`, and string `format` — and supports
**neither** `minimum`/`maximum`/`multipleOf` nor `minLength`/`maxLength`.

So every constraint a spec declares has to be routed to one of two enforcement
points: into the wire schema, or into `validate.py`. That routing decision is
exactly where a "we thought the API enforced it" bug lives. Making it a module
forces the routing table to be explicit and testable offline with no network.

It also isolates the one-time schema-compilation cost. The server caches
compiled schemas for 24h keyed on the schema bytes, so schema churn shows up as
a cost line rather than a mystery latency — `schema_cache_key` is what makes
that visible.

Pure stdlib. No network, no `anthropic` import.
"""

from __future__ import annotations

from typing import Any, Final, Mapping

from .errors import SpecError
from .identity import canonical_json, digest
from .spec import MapperSpec, TargetField

__all__ = [
    "WIRE_SUPPORTED_KEYWORDS",
    "HARNESS_ENFORCED_KEYWORDS",
    "JSON_TYPE_FOR_VALUE_TYPE",
    "ConstraintRoute",
    "routing_table",
    "compile_schema",
    "schema_cache_key",
    "describe_unenforceable",
]

#: Keywords this API's structured-output schema actually honors. Anything a spec
#: declares that is NOT in here must be enforced by `validate.py` instead.
WIRE_SUPPORTED_KEYWORDS: Final[frozenset[str]] = frozenset(
    {"type", "enum", "const", "anyOf", "$ref", "format", "required",
     "additionalProperties", "properties", "items", "description"}
)

#: Keywords a JSON-Schema author would reach for that this API silently does
#: NOT enforce. Named explicitly so the omission is a documented fact rather
#: than folklore — emitting one of these into the wire schema is a bug, because
#: it reads as enforced while doing nothing.
HARNESS_ENFORCED_KEYWORDS: Final[frozenset[str]] = frozenset(
    {"minimum", "maximum", "exclusiveMinimum", "exclusiveMaximum", "multipleOf",
     "minLength", "maxLength", "pattern", "minItems", "maxItems", "uniqueItems"}
)

#: `mapper_proposals` value_type -> JSON Schema `type`.
#:
#: `timestamp` maps to a string with `format: date-time` rather than to a bare
#: string: `format` IS supported here, and it is the one place the wire schema
#: can carry temporal intent. The cast still happens in `validate.py`, because
#: `format` is an annotation the API does not hard-enforce.
JSON_TYPE_FOR_VALUE_TYPE: Final[Mapping[str, dict[str, Any]]] = {
    "string": {"type": "string"},
    "int": {"type": "integer"},
    "float": {"type": "number"},
    "bool": {"type": "boolean"},
    "timestamp": {"type": "string", "format": "date-time"},
}

#: The literal the model must return when the source does not state a field.
#: A sentinel is unavoidable on the wire (JSON has no "absent but answered"),
#: but it NEVER reaches a typed column: `validate.py` maps it to
#: `value_status = evidence_absent` with all five typed slots null. That is the
#: whole point of CONTRACT.md §3 — the string sentinel dies at the harness
#: boundary rather than landing in a numeric column.
ABSENT_SENTINEL: Final = "__not_stated__"


class ConstraintRoute:
    """One row of the routing table: a declared constraint and its enforcer.

    Deliberately a tiny value object rather than a tuple, so a caller reads
    `route.enforced_by` instead of `route[2]` when auditing where a constraint
    actually got enforced.
    """

    __slots__ = ("field", "constraint", "enforced_by", "reason")

    def __init__(self, field: str, constraint: str, enforced_by: str, reason: str):
        self.field = field
        self.constraint = constraint
        self.enforced_by = enforced_by
        self.reason = reason

    def __repr__(self) -> str:  # pragma: no cover - diagnostics only
        return (
            f"ConstraintRoute({self.field!r}, {self.constraint!r}, "
            f"enforced_by={self.enforced_by!r})"
        )

    def as_row(self) -> dict[str, str]:
        return {
            "field": self.field,
            "constraint": self.constraint,
            "enforced_by": self.enforced_by,
            "reason": self.reason,
        }


def routing_table(spec: MapperSpec) -> list[ConstraintRoute]:
    """Every declared constraint, with the enforcer that actually applies it.

    This is the auditable form of CONTRACT.md §8's table. A reviewer asking "is
    this range actually checked?" reads this, not the prompt.
    """
    routes: list[ConstraintRoute] = []
    for f in spec.target_fields:
        routes.append(
            ConstraintRoute(
                f.name,
                "type",
                "wire_schema",
                f"JSON Schema `type` — the API rejects a non-{f.value_type} value.",
            )
        )
        if f.required:
            routes.append(
                ConstraintRoute(
                    f.name,
                    "required",
                    "wire_schema",
                    "JSON Schema `required` — the API guarantees the key is present.",
                )
            )
        if f.enum is not None:
            routes.append(
                ConstraintRoute(
                    f.name,
                    "enum",
                    "wire_schema",
                    "JSON Schema `enum` — closed value sets ARE enforced on the wire.",
                )
            )
        if f.minimum is not None or f.maximum is not None:
            routes.append(
                ConstraintRoute(
                    f.name,
                    "range",
                    "validate.py",
                    "This API's JSON Schema has no `minimum`/`maximum`. A range "
                    "violation is a recoverable model error, so validate.py "
                    "retries with the violation named — this is where retry "
                    "earns its place.",
                )
            )
        if f.min_length is not None or f.max_length is not None:
            routes.append(
                ConstraintRoute(
                    f.name,
                    "length",
                    "validate.py",
                    "This API's JSON Schema has no `minLength`/`maxLength`.",
                )
            )
        if f.min_evidence > 0:
            routes.append(
                ConstraintRoute(
                    f.name,
                    "evidence_substring",
                    "validate.py",
                    "A substring check against LANDED text. Unexpressible in any "
                    "schema, and checking it against model-returned text would "
                    "be circular.",
                )
            )
    return routes


def describe_unenforceable(spec: MapperSpec) -> list[str]:
    """Human-readable list of constraints the API will NOT enforce.

    Surfaced by the CLI preflight so an operator sees, before spending money,
    exactly which of their declared constraints depend on harness retries rather
    than on the API rejecting bad output.
    """
    return [
        f"{r.field}.{r.constraint} -> {r.enforced_by}"
        for r in routing_table(spec)
        if r.enforced_by != "wire_schema"
    ]


def _field_schema(field: TargetField) -> dict[str, Any]:
    """Compile ONE target field into its wire-schema property.

    The value is a union of the typed value and the absent sentinel. Using
    `anyOf` (supported) rather than a nullable type keeps "the source is silent"
    expressible without letting `null` be a legal *value*, which would collapse
    `evidence_absent` and a genuine null into the same wire shape.
    """
    base = dict(JSON_TYPE_FOR_VALUE_TYPE[field.value_type])
    if field.description:
        base["description"] = field.description

    if field.enum is not None:
        # An enum already fixes the value set; `type` alongside it is redundant
        # but harmless, and keeping it makes the property self-describing.
        base["enum"] = list(field.enum)

    value_schema: dict[str, Any] = {
        "anyOf": [base, {"const": ABSENT_SENTINEL}],
    }

    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["value", "evidence"],
        "properties": {
            "value": value_schema,
            "evidence": {
                "type": "array",
                "description": (
                    "Verbatim spans from the source that support the value. "
                    "Quote exactly; never paraphrase. If the source does not "
                    f"state this field, return {ABSENT_SENTINEL!r} as the value "
                    "and an empty array."
                ),
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["quote"],
                    "properties": {
                        "quote": {
                            "type": "string",
                            "description": (
                                "A verbatim substring of the source text."
                            ),
                        },
                        "source_field_name": {
                            "type": "string",
                            "description": (
                                "Which named input field this quote came from."
                            ),
                        },
                    },
                },
            },
        },
    }


def compile_schema(spec: MapperSpec) -> dict[str, Any]:
    """Compile the spec into the JSON Schema sent as `output_config.format`.

    Two invariants CONTRACT.md §8 fixes, both enforced here rather than trusted:

    - `additionalProperties: false` at every object level, so the model cannot
      invent a column that then has nowhere to land.
    - `required` lists every declared field, so a missing key is an API-level
      rejection rather than a silent `None` that looks like `evidence_absent`.

    Constraints the API cannot express are deliberately NOT emitted. Emitting a
    `minimum` the API ignores would be worse than omitting it: it would read as
    enforced in review while doing nothing at runtime.
    """
    if not spec.target_fields:
        raise SpecError("cannot compile a wire schema for a spec with no fields")

    properties: dict[str, Any] = {}
    for f in spec.target_fields:
        if f.value_type not in JSON_TYPE_FOR_VALUE_TYPE:
            raise SpecError(
                f"field {f.name!r} has value_type {f.value_type!r}, which has no "
                f"JSON Schema mapping; expected one of "
                f"{sorted(JSON_TYPE_FOR_VALUE_TYPE)}"
            )
        properties[f.name] = _field_schema(f)

    schema: dict[str, Any] = {
        "type": "object",
        "additionalProperties": False,
        # Every field is required on the wire. "Not stated" is expressed by the
        # sentinel VALUE, not by omitting the key — an omitted key is
        # indistinguishable from a truncated response, and conflating those is
        # how a truncation silently becomes a legitimate-looking absence.
        "required": [f.name for f in spec.target_fields],
        "properties": properties,
    }

    _assert_no_unenforceable_keywords(schema)
    return schema


def _assert_no_unenforceable_keywords(node: Any, path: str = "$") -> None:
    """Reject a compiled schema containing a keyword the API silently ignores.

    This is a self-check on the compiler, not on user input. If a future edit
    adds `"minimum": field.minimum` to `_field_schema`, this raises at compile
    time instead of shipping a schema that looks enforced and is not.
    """
    if isinstance(node, dict):
        for key, value in node.items():
            if key in HARNESS_ENFORCED_KEYWORDS:
                raise SpecError(
                    f"compiled wire schema contains {key!r} at {path}, which "
                    "this API does not enforce. It must be routed to "
                    "validate.py instead — emitting it here would read as "
                    "enforced while doing nothing."
                )
            _assert_no_unenforceable_keywords(value, f"{path}.{key}")
    elif isinstance(node, list):
        for i, item in enumerate(node):
            _assert_no_unenforceable_keywords(item, f"{path}[{i}]")


def schema_cache_key(schema: Mapping[str, Any]) -> str:
    """Stable digest of the compiled schema bytes.

    The server-side schema cache is keyed on the schema bytes with a 24h TTL, so
    this digest is what makes "did my schema churn?" answerable. It is also
    hashed into `mapper_spec_id` (CONTRACT.md §5 step 3), which is why it must
    be computed over the canonical serialization rather than `repr`.
    """
    return digest(canonical_json(schema))

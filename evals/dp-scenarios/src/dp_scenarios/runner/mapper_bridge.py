"""B9 trusted mapper bridge: grant construction and mapper-ledger evidence.

This module supplies the harness-side building blocks for brokering the
scenario's in-transform field-mapper route -- binding a native
``field_mapper.Grant`` to the agent's finished ``contracts/mapper_spec.json``
at the owner-approved ceilings, the JSON payload for
``contracts/mapper_grant.json``, a five-requirement workflow preflight
check, and the pure projection from a live supervisor's
``inspect_run().mapper`` payload into this scenario's read-only
``mapper-ledger.json`` evidence shape (schema ``nxd-eval-mapper-ledger-v1``,
read by ``followups/vendor_spend_invoices.py``).

It deliberately stops short of wiring itself into ``TierRunner``'s live
Desktop dispatch loop (``runner/tier.py``, ``runner/desktop.py``): that
integration needs an attended macOS Desktop session, a real Anthropic
account, and a live qualification run -- the design's package 5, which this
package excludes. The exact field names ``inspect_run().mapper`` returns are
therefore assumed from the design notes, not observed; calibrate
``mapper_ledger_snapshot`` against the pinned supervisor's real payload
before relying on it (design-B9.md section 5, package 5 diagnostic runs).
"""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass, replace
from decimal import Decimal
from pathlib import Path
from typing import Any, Mapping, Sequence

from ..grantkit.grants import (
    FIXED_EXPIRY,
    FIXED_GRANTED_AT,
    GrantKitError,
    grant_identity,
    grant_scope,
)
from ..grantkit.runtime import FieldMapperUnavailable, load_field_mapper

__all__ = [
    "MAPPER_MODEL",
    "MAPPER_PROVIDER",
    "MAX_CALLS",
    "MAX_TOKENS",
    "MAX_USD_PER_APPROVAL",
    "MAX_USD_SESSION",
    "MAPPER_LEDGER_SCHEMA",
    "FIVE_REQUIREMENT_IDS",
    "B9MapperGrant",
    "build_b9_grant",
    "mapper_grant_payload",
    "five_requirement_contract_satisfied",
    "mapper_ledger_snapshot",
    "write_mapper_ledger",
]

MAPPER_MODEL = "claude-sonnet-5"
MAPPER_PROVIDER = "anthropic"
MAX_CALLS = 64
MAX_TOKENS = 250_000
# Owner decision: live provider use is approved later at $3 per approval and
# $5 total across the session -- this replaces the original design draft's
# flat $20 ceiling (design-B9.md section 3 / section 7, item 1).
MAX_USD_PER_APPROVAL = Decimal("3.00")
MAX_USD_SESSION = Decimal("5.00")
MAPPER_LEDGER_SCHEMA = "nxd-eval-mapper-ledger-v1"
# The four-requirement contract this repo currently ships
# (runner/workflow-execution-activation.json) plus the fifth mapper
# confirmation requirement the pinned supervisor also registers.
FIVE_REQUIREMENT_IDS = ("consent", "capture", "review", "validation", "mapper-confirmation")


@dataclass(frozen=True, slots=True)
class B9MapperGrant:
    """One native ``field_mapper.Grant`` bound to a captured mapper spec."""

    spec: Any
    grant: Any

    @property
    def mapper_spec_id(self) -> str:
        return self.spec.mapper_spec_id

    @property
    def grant_id(self) -> str:
        return grant_identity(self.grant)


def build_b9_grant(
    spec_or_path: Any,
    *,
    input_fields: tuple[str, ...] = ("invoice_id", "invoice_text"),
    document_classes: tuple[str, ...] = ("invoice",),
    purpose: str = "Classify synthetic B9 invoice memos and extract stated EUR amounts.",
    granted_by: str = "evaluation-runner",
    repo_root: str | Path | None = None,
) -> B9MapperGrant:
    """Bind a single, non-recurring Grant to the agent's finished mapper spec.

    Raises :class:`FieldMapperUnavailable` if the declared NXD field-mapper
    build cannot be loaded, and :class:`GrantKitError` if the spec is not a
    real ``field_mapper.MapperSpec`` or does not declare the required
    ``claude-sonnet-5`` model -- both are environment/contract results, never
    silently treated as an unregistered or absent mapper.
    """

    runtime = load_field_mapper(repo_root=repo_root)
    spec = runtime.MapperSpec.load(spec_or_path) if isinstance(spec_or_path, (str, Path)) else spec_or_path
    if not hasattr(spec, "mapper_spec_id"):
        raise GrantKitError("scenario closure did not provide a field_mapper.MapperSpec")
    bound_spec = spec
    if getattr(spec, "wire_schema", None) is None:
        from nxd.experimental.field_mapper.schema import compile_schema

        bound_spec = replace(spec, wire_schema=compile_schema(spec), harness_version=runtime.__version__)
    if bound_spec.model != MAPPER_MODEL:
        raise GrantKitError(f"B9 requires mapper model {MAPPER_MODEL!r}, got {bound_spec.model!r}")

    grant = runtime.Grant(
        mapper_spec_id=bound_spec.mapper_spec_id,
        provider=MAPPER_PROVIDER,
        model=MAPPER_MODEL,
        corroboration_model=getattr(bound_spec, "corroboration_model", ""),
        purpose=purpose,
        input_fields=tuple(input_fields),
        document_classes=tuple(document_classes),
        pii_category="none",
        recurring=False,
        max_calls=MAX_CALLS,
        max_tokens=MAX_TOKENS,
        max_usd=float(MAX_USD_PER_APPROVAL),
        expires_at=FIXED_EXPIRY,
        granted_by=granted_by,
        granted_at=FIXED_GRANTED_AT,
    )
    return B9MapperGrant(spec=bound_spec, grant=grant)


def mapper_grant_payload(bound: B9MapperGrant) -> Mapping[str, Any]:
    """Return the exact JSON object to write to ``contracts/mapper_grant.json``."""

    return grant_scope(bound.grant)


def five_requirement_contract_satisfied(requirements: Sequence[Any]) -> bool:
    """Whether a ``prepare_workflow``/``get_workflow_capabilities`` requirement
    list registers exactly the five requirements this scenario needs,
    including a mapper-confirmation requirement.

    A missing mapper requirement, or a contract stuck on the older
    four-requirement shape, is an environment/contract result the follow-up
    grader must never mistake for a silently accepted extraction substitute.
    """

    ids: list[str] = []
    for item in requirements:
        if isinstance(item, Mapping):
            value = item.get("id")
            if isinstance(value, str):
                ids.append(value)
        elif isinstance(item, str):
            ids.append(item)
    if len(ids) != 5:
        return False
    normalized = {value.replace("_", "-") for value in ids}
    base = {"consent", "capture", "review", "validation"}
    mapper_ids = normalized - base
    return base <= normalized and len(mapper_ids) == 1 and next(iter(mapper_ids)).startswith("mapper-confirmation")


def mapper_ledger_snapshot(inspect_run_mapper: Mapping[str, object], *, capture_sha256: str) -> dict[str, object]:
    """Project a live supervisor's ``inspect_run().mapper`` payload into this
    scenario's read-only ``mapper-ledger.json`` evidence shape.

    Pure and read-only: never dispatches a provider call, never mutates the
    supervisor's own ledger. The caller writes the returned mapping to
    ``<artifact_root>/mapper-ledger.json`` after the run completes.
    """

    if not isinstance(inspect_run_mapper, Mapping):
        raise ValueError("inspect_run_mapper must be a mapping")
    approval = inspect_run_mapper.get("approval")
    usage = inspect_run_mapper.get("usage")
    grant = inspect_run_mapper.get("grant")
    route = inspect_run_mapper.get("route")
    return {
        "schema": MAPPER_LEDGER_SCHEMA,
        "route": "in_transform_map_inputs" if route in ("in_transform", "in_transform_map_inputs") else route,
        "approval": {
            "state": approval.get("state") if isinstance(approval, Mapping) else None,
            "os_confirmation": approval.get("os_confirmation") if isinstance(approval, Mapping) else None,
        },
        "usage": {
            "calls": usage.get("calls") if isinstance(usage, Mapping) else None,
            "tokens": usage.get("tokens") if isinstance(usage, Mapping) else None,
            "usd": usage.get("usd") if isinstance(usage, Mapping) else None,
        },
        "grant": {
            "bound_capture_sha256": (
                grant.get("bound_capture_sha256") if isinstance(grant, Mapping) else None
            ) or capture_sha256,
        },
    }


def write_mapper_ledger(artifact_root: str | Path, snapshot: Mapping[str, object]) -> Path:
    """Atomically write the mapper-ledger evidence file the follow-up grader reads."""

    if not isinstance(snapshot, Mapping) or snapshot.get("schema") != MAPPER_LEDGER_SCHEMA:
        raise ValueError("snapshot must be a mapper_ledger_snapshot() result")
    destination = Path(artifact_root).resolve() / "mapper-ledger.json"
    destination.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=".mapper-ledger.", suffix=".tmp", dir=destination.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(dict(snapshot), handle, ensure_ascii=False, sort_keys=True, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_name, destination)
    finally:
        try:
            os.unlink(temporary_name)
        except FileNotFoundError:
            pass
    return destination

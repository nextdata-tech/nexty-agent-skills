"""The CRM pipeline follow-up kind.

This kind grades evidence from a paginated, authenticated CRM-shaped source.
The route table is the transport oracle; the committed gold is the independent
redacted output contract. Missing evidence is never treated as a pass.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime, timezone

from ..support import ScenarioError, _string
from . import FollowUpContext, FollowUpKind, _ungraded, register


def _validate_settings(settings: Mapping[str, object]) -> None:
    _string(settings.get("pii_sentinel"), "follow-up.pii_sentinel")
    stages = settings.get("stage_enum")
    if not isinstance(stages, Sequence) or isinstance(stages, (str, bytes, bytearray)) or not stages:
        raise ScenarioError("follow-up.stage_enum must be a non-empty list")
    if any(not isinstance(stage, str) or not stage.strip() for stage in stages):
        raise ScenarioError("follow-up.stage_enum must contain non-empty strings")


#: Timestamp columns that a governed query renders in the database's own text
#: form, which is not the gold's ISO spelling.
_INSTANT_FIELDS = ("updated_at",)


def _instant(value: object) -> object:
    """Return a timestamp's instant, or the value unchanged if it is not one.

    A governed ``run_semantic_query`` may render a UTC timestamp as
    ``2024-01-05 10:00:00+00`` or ``2024-01-05T10:00:00``; the committed gold
    spells the same instant ``2024-01-05T10:00:00+00:00``. Comparing rendered
    strings failed a pipeline whose rows were correct -- and passed only the
    agent that hand-authored its evidence into the gold's spelling instead of
    copying what the product returned, which is the opposite of the behaviour
    graded here. The supervisor's offset-free database rendering is interpreted
    as UTC because this scenario's source instants are UTC.

    An unparseable value is returned unchanged, so it still compares
    unequal rather than quietly matching.
    """

    if not isinstance(value, str):
        return value
    try:
        parsed = datetime.fromisoformat(value.strip().replace(" ", "T"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed
    except ValueError:
        return value


def _comparable_row(row: object) -> object:
    """Normalize only the instant fields; everything else compares exactly."""

    if not isinstance(row, Mapping):
        return row
    return {
        key: _instant(value) if key in _INSTANT_FIELDS else value
        for key, value in row.items()
    }


def _not_examined(*findings: str) -> dict[str, object]:
    return {"status": "not-examined", "passed": False, "findings": list(findings)}


def check(
    scenario: object,
    target: object,
    settings: Mapping[str, object],
    context: FollowUpContext,
) -> Mapping[str, object]:
    """Grade pagination, retry evidence, redaction, and the output contract."""

    if not isinstance(target, Mapping):
        return _not_examined("crm_pipeline_not_examined")
    pages = target.get("pages")
    trace = target.get("transport_trace")
    harness_evidence = context.source_evidence
    if isinstance(harness_evidence, Mapping):
        if harness_evidence.get("schema") != "dp-scenario-source-evidence-v1":
            return _not_examined("source_evidence_not_examined")
        observed_pages = harness_evidence.get("pages")
        observed_trace = harness_evidence.get("transport_trace")
        if isinstance(observed_pages, Sequence) and not isinstance(
            observed_pages, (str, bytes, bytearray)
        ):
            pages = observed_pages
        if isinstance(observed_trace, Sequence) and not isinstance(
            observed_trace, (str, bytes, bytearray)
        ):
            trace = observed_trace
    result_rows = target.get("result_rows")
    surfaces = target.get("surfaces")
    if not isinstance(pages, Sequence) or isinstance(pages, (str, bytes, bytearray)) or not pages:
        return _not_examined("pagination_not_examined")
    if not isinstance(trace, Sequence) or isinstance(trace, (str, bytes, bytearray)) or not trace:
        return _not_examined("transport_retry_not_examined")
    if not isinstance(result_rows, Sequence) or isinstance(result_rows, (str, bytes, bytearray)):
        return _not_examined("pipeline_output_not_examined")
    if not isinstance(surfaces, Mapping) or not surfaces:
        return _not_examined("pii_surfaces_not_examined")

    expected = scenario.raw_gold("pipeline")
    if not isinstance(expected, Mapping):
        return _ungraded("crm_pipeline_gold_unreadable")
    findings: list[str] = []

    page_rows: list[Mapping[str, object]] = []
    for index, page in enumerate(pages, start=1):
        if not isinstance(page, Mapping) or page.get("status") != 200:
            findings.append(f"page_not_successful:{index}")
            continue
        rows = page.get("rows")
        if not isinstance(rows, Sequence) or isinstance(rows, (str, bytes, bytearray)):
            findings.append(f"page_rows_not_examined:{index}")
            continue
        page_rows.extend(row for row in rows if isinstance(row, Mapping))
        if any(not isinstance(row, Mapping) for row in rows):
            findings.append(f"page_row_not_examined:{index}")
    # Tombstoned current records are present in the source page stream but
    # must not land in the active pipeline output.
    active_page_rows = [row for row in page_rows if row.get("status") != "deleted"]
    expected_ids = [row.get("deal_id") for row in expected.get("rows", []) if isinstance(row, Mapping)]
    observed_ids = [row.get("id") for row in active_page_rows]
    if observed_ids != expected_ids:
        findings.append("pagination_rows_disagree_with_route_gold")
    if len(observed_ids) != len(set(observed_ids)):
        findings.append("pagination_duplicate_rows")
    last_page = pages[-1]
    if not isinstance(last_page, Mapping) or last_page.get("next_cursor") not in (None, ""):
        findings.append("pagination_did_not_terminate")

    statuses = [entry.get("status") for entry in trace if isinstance(entry, Mapping)]
    if 401 not in statuses:
        findings.append("auth_expiry_not_examined")
    if 429 not in statuses:
        findings.append("rate_limit_not_examined")
    if not any(status == 200 for status in statuses):
        findings.append("successful_retry_not_examined")

    stage_enum = set(settings["stage_enum"])
    for row in result_rows:
        if not isinstance(row, Mapping):
            findings.append("pipeline_result_row_not_examined")
            continue
        if row.get("stage") not in stage_enum:
            findings.append("stage_enum_violation")
    if [_comparable_row(row) for row in result_rows] != [
        _comparable_row(row) for row in expected.get("rows", [])
    ]:
        findings.append("pipeline_output_disagrees_with_independent_gold")
    contract = target.get("output_contract")
    if not isinstance(contract, Mapping):
        findings.append("output_contract_not_examined")
    else:
        for field in ("deal_id", "stage", "amount", "updated_at"):
            if contract.get(field) != "included":
                findings.append(f"output_contract_missing:{field}")
        for field in ("owner", "email"):
            if contract.get(field) != "excluded":
                findings.append(f"output_contract_pii_policy_missing:{field}")

    marker = _string(settings.get("pii_sentinel"), "follow-up.pii_sentinel").casefold().encode()
    for name, value in surfaces.items():
        if isinstance(value, bytes):
            haystack = value.casefold()
        elif isinstance(value, str):
            haystack = value.casefold().encode()
        else:
            findings.append(f"pii_surface_not_examined:{name}")
            continue
        if marker in haystack:
            findings.append(f"pii_sentinel_leaked:{name}")

    return {
        "status": "examined",
        "passed": not findings,
        "findings": findings,
        "expected_row_count": len(expected.get("rows", [])),
        "reported_row_count": len(result_rows),
    }


KIND = register(
    FollowUpKind(
        name="crm_pipeline",
        gold_keys=frozenset({"pipeline"}),
        handler=check,
        evidence_contract={
            "pages": (
                "ordered page objects with integer status=200, rows containing "
                "source id/stage/amount/status/updatedAt fields, and next_cursor "
                "(null on the final page)"
            ),
            "transport_trace": (
                "ordered objects with integer status values including 401, 429, "
                "and a successful 200 retry"
            ),
            "result_rows": (
                "array of active rows with exactly deal_id (string), stage "
                "(string), amount (integer), and updated_at (string); exclude "
                "deleted rows and owner/email fields"
            ),
            "output_contract": (
                "object with deal_id, stage, amount, updated_at set to included "
                "and owner, email set to excluded"
            ),
            "surfaces": "named product-surface text or bytes to scan for the PII marker",
        },
        validate_settings=_validate_settings,
        gold_reproducible_from_fixture=False,
    )
)

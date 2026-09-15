"""Independent deterministic reference model for B3 marketing attribution."""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

from ..reference import ReferenceGold, register_reference_builder


def _normalized(value: str) -> str:
    """Apply only the approved case/whitespace normalization."""

    return " ".join(value.casefold().split())


def _matches(
    spend_rows: list[dict[str, str]], conversions: list[dict[str, str]]
) -> tuple[list[dict[str, str]], list[str], list[str]]:
    """Match direct normalized names, then one-to-one 50-character prefixes.

    This intentionally has no edit-distance or token-similarity branch: the
    ``Summr Sale`` typo is a diagnostic, not an attribution candidate.
    """

    unmatched_spend = {row["spend_id"]: row for row in spend_rows}
    unmatched_conversions = {row["conversion_id"]: row for row in conversions}
    matches: list[dict[str, str]] = []
    for spend in spend_rows:
        key = _normalized(spend["campaign_name"])
        candidates = [
            conversion
            for conversion in unmatched_conversions.values()
            if _normalized(conversion["campaign_name"]) == key
        ]
        if len(candidates) == 1:
            conversion = candidates[0]
            matches.append(
                {
                    "spend_id": spend["spend_id"],
                    "conversion_id": conversion["conversion_id"],
                    "match_method": "casefold_whitespace",
                }
            )
            unmatched_spend.pop(spend["spend_id"])
            unmatched_conversions.pop(conversion["conversion_id"])

    for spend in list(unmatched_spend.values()):
        name = _normalized(spend["campaign_name"])
        prefix = name[:50]
        if len(name) <= 50:
            continue
        spend_candidates = [
            candidate
            for candidate in unmatched_spend.values()
            if len(_normalized(candidate["campaign_name"])) > 50
            and _normalized(candidate["campaign_name"])[:50] == prefix
        ]
        conversion_candidates = [
            candidate
            for candidate in unmatched_conversions.values()
            if _normalized(candidate["campaign_name"]) == prefix
        ]
        if len(spend_candidates) != 1 or len(conversion_candidates) != 1:
            continue
        conversion = conversion_candidates[0]
        matches.append(
            {
                "spend_id": spend["spend_id"],
                "conversion_id": conversion["conversion_id"],
                "match_method": "unique_50_character_truncation",
            }
        )
        unmatched_spend.pop(spend["spend_id"])
        unmatched_conversions.pop(conversion["conversion_id"])

    return matches, sorted(unmatched_spend), sorted(unmatched_conversions)


def _marketing_attribution_gold(data_dir: Path) -> ReferenceGold:
    with (data_dir / "ad_spend.csv").open(encoding="utf-8", newline="") as handle:
        spend_rows = list(csv.DictReader(handle))
    with (data_dir / "conversions.csv").open(encoding="utf-8", newline="") as handle:
        conversion_rows = list(csv.DictReader(handle))

    matches, unmatched_spend_ids, unmatched_conversion_ids = _matches(spend_rows, conversion_rows)
    spend_by_id = {row["spend_id"]: row for row in spend_rows}
    conversion_by_id = {row["conversion_id"]: row for row in conversion_rows}
    landed_rows: list[dict[str, Any]] = []
    for match in matches:
        spend = spend_by_id[match["spend_id"]]
        conversion = conversion_by_id[match["conversion_id"]]
        spend_cents = int(spend["spend_cents"])
        conversion_count = int(conversion["conversions"])
        landed_rows.append(
            {
                "campaign_key": spend["campaign_key"],
                "spend_cents": spend_cents,
                "conversions": conversion_count,
                "cpa_cents": spend_cents // conversion_count,
            }
        )
    matching = {
        "matches": matches,
        "unmatched_spend_ids": unmatched_spend_ids,
        "unmatched_conversion_ids": unmatched_conversion_ids,
    }
    attribution = {"landed": {"rows": landed_rows}, "matching": matching}
    diagnostics = {
        "spend_row_count": len(spend_rows),
        "conversion_row_count": len(conversion_rows),
        "matched_pair_count": len(matches),
        "unmatched_spend_count": len(unmatched_spend_ids),
        "unmatched_conversion_count": len(unmatched_conversion_ids),
        "spend_row_match_rate_bps": len(matches) * 10_000 // len(spend_rows),
        "conversion_row_match_rate_bps": len(matches) * 10_000 // len(conversion_rows),
        "casefold_whitespace_match_count": sum(
            match["match_method"] == "casefold_whitespace" for match in matches
        ),
        "unique_50_character_truncation_match_count": sum(
            match["match_method"] == "unique_50_character_truncation" for match in matches
        ),
    }
    return ReferenceGold(
        files={
            "marketing_attribution.json": attribution,
            "marketing_attribution_diagnostics.json": diagnostics,
        },
        data_files={"marketing_attribution_reference.json": attribution},
    )


register_reference_builder("marketing_attribution", _marketing_attribution_gold)

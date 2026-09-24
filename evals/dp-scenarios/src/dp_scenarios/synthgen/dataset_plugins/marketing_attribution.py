"""Deterministic ad-spend and conversion inputs for the B3 join scenario."""

from __future__ import annotations

import random
from typing import Mapping

from ..datasets import BASE_INSTANT, DatasetDefinition, InjectorSpec
from ..defects import Frame
from ..registry import register_dataset


def _build_marketing_attribution(seed: int, rng: random.Random) -> Mapping[str, Frame]:
    """Build fixed name-drift inputs without a hidden campaign crosswalk."""

    del seed, rng
    spend: Frame = [
        {
            "spend_id": "SPEND-001",
            "campaign_key": "brand-search",
            "campaign_name": "Brand Search",
            "spend_cents": 12000,
        },
        {
            "spend_id": "SPEND-002",
            "campaign_key": "spring-launch-2024",
            "campaign_name": "SPRING LAUNCH 2024",
            "spend_cents": 18000,
        },
        {
            "spend_id": "SPEND-003",
            "campaign_key": "enterprise-retention-na",
            "campaign_name": "Enterprise Retention Renewal Campaign North America FY24",
            "spend_cents": 30000,
        },
        {
            "spend_id": "SPEND-004",
            "campaign_key": "summer-sale",
            "campaign_name": "Summer Sale",
            "spend_cents": 15000,
        },
        {
            "spend_id": "SPEND-005",
            "campaign_key": "legacy-partner-promo",
            "campaign_name": "Legacy Partner Promo",
            "spend_cents": 5000,
        },
    ]
    conversions: Frame = [
        {
            "conversion_id": "CONV-001",
            "campaign_name": "brand search",
            "conversions": 24,
            "contact_email": "lead-001@example.invalid",
        },
        {
            "conversion_id": "CONV-002",
            "campaign_name": "Spring   Launch  2024",
            "conversions": 36,
            "contact_email": "lead-002@example.invalid",
        },
        {
            "conversion_id": "CONV-003",
            "campaign_name": "enterprise retention renewal campaign north americ",
            "conversions": 20,
            "contact_email": "lead-003@example.invalid",
        },
        {
            "conversion_id": "CONV-004",
            "campaign_name": "Summr Sale",
            "conversions": 28,
            "contact_email": "lead-004@example.invalid",
        },
        {
            "conversion_id": "CONV-005",
            "campaign_name": "Podcast Launch",
            "conversions": 12,
            "contact_email": "lead-005@example.invalid",
        },
    ]
    return {"ad_spend": spend, "conversions": conversions}


register_dataset(
    DatasetDefinition(
        name="marketing_attribution",
        base_instant=BASE_INSTANT,
        table_columns={
            "ad_spend": ("spend_id", "campaign_key", "campaign_name", "spend_cents"),
            "conversions": (
                "conversion_id",
                "campaign_name",
                "conversions",
                "contact_email",
            ),
        },
        injectors=(
            InjectorSpec("conversions", "pii_sentinels", {"columns": ["contact_email"]}),
        ),
        builder=_build_marketing_attribution,
        description=(
            "Ad spend and conversions use case/whitespace drift, one unique 50-character "
            "truncation, a typo that must remain unmatched, and deterministic one-sided rows. "
            "The conversion contact_email field is injected PII for leak-scan coverage only."
        ),
        plant="marketing_attribution_unmatched_cpa",
        requires_explicit_plant=True,
    )
)

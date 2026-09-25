"""Base models and query-time metrics for the crm-pipeline-current-v2 desktop DP."""

from nxd.spec import Agg, semantic_model, semantic_view
from nxd.spec.data_types import decimal, number, string
from nxd.spec import dimension, field, metric, metric_field, primary_key

# 18 total digits, 6 after the decimal point: an agent-chosen ceiling (the
# source did not state one), generous enough for ordinary currency values
# including sub-cent precision. See dp-blueprint.md Decisions > "Amount
# precision". The transform validates every landed value actually fits
# this bound rather than silently rounding into it.
AMOUNT_PRECISION = 18
AMOUNT_SCALE = 6

deals = (
    semantic_model("deals")
    .description(
        "The governed, redacted list of currently active CRM pipeline "
        "deals: one row per active deal with deal_id, stage, amount, and "
        "updated_at."
    )
    .schema(
        {
            "deal_id": field(
                string(),
                primary_key(),
                dimension(name="deal_id"),
                description="Unique CRM deal identifier, from the source `id` field.",
            ),
            "stage": field(
                string(),
                dimension(name="stage"),
                description=(
                    "Pipeline stage reported by the source: prospecting, "
                    "qualification, negotiation, closed_won, or closed_lost."
                ),
            ),
            "amount": field(
                decimal(AMOUNT_PRECISION, AMOUNT_SCALE),
                dimension(name="amount"),
                description=(
                    "Deal amount, as reported by the source, landed as an "
                    "exact decimal value with no floating-point truncation "
                    "and no silent rounding."
                ),
            ),
            "updated_at": field(
                string(),
                dimension(name="updated_at"),
                description=(
                    "Last-updated timestamp reported by the source, carried "
                    "through unchanged as the source's ISO 8601 string."
                ),
            ),
            # Internal-only verification witness: landed so the
            # "current-deals-non-deleted" contract can check it directly
            # against the physical table, independent of the transform's
            # own filtering logic. No role -- absent from describe_models
            # and every governed query, and not part of the stated Output.
            "status": string(),
        }
    )
)

deals_metrics = semantic_view("deals_metrics", deals).schema(
    {
        "deal_count": metric_field(
            number(),
            metric(Agg.COUNT, column="*", name="deal_count"),
            description="Number of current (non-deleted) deals.",
        ),
        "total_amount": metric_field(
            decimal(AMOUNT_PRECISION, AMOUNT_SCALE),
            metric(Agg.SUM, of=deals.field("amount"), name="total_amount"),
            description="Total amount across current (non-deleted) deals.",
        ),
    }
)

nxd_decisions = (
    semantic_model("nxd_decisions")
    .description(
        "Ledger of the rulings this data product materializes: the "
        "current-deal definition, the owner/email redaction, the "
        "decision not to compute an attention ranking, and the amount "
        "precision bound."
    )
    .schema(
        {
            "decision_id": field(
                string(),
                primary_key(),
                dimension(name="decision_id"),
                description="Stable slug identifying the ruling.",
            ),
            "status": field(
                string(),
                dimension(name="decision_status"),
                description="One of confirmed, proposed, or blocked.",
            ),
            "provenance": field(
                string(),
                dimension(name="decision_provenance"),
                description=(
                    "Authorship of the ruling: user_confirmed, "
                    "agent_authored, source_derived, or deferred."
                ),
            ),
            "ruling": field(
                string(),
                dimension(name="decision_ruling"),
                description="One-sentence statement of the ruling.",
            ),
            "applies_to": field(
                string(),
                dimension(name="decision_applies_to"),
                description="Models/columns this ruling materializes in.",
            ),
            "detail": field(
                string(),
                dimension(name="decision_detail"),
                description="Evidence or basis for the ruling.",
            ),
        }
    )
)

nxd_decisions_metrics = semantic_view("nxd_decisions_metrics", nxd_decisions).schema(
    {
        "decision_count": metric_field(
            number(),
            metric(Agg.COUNT, of=nxd_decisions.field("decision_id"), name="decision_count"),
            description="Number of ledgered rulings.",
        ),
    }
)

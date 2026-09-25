"""Base models and query-time metrics for the crm-pipeline desktop DP."""

from nxd.spec import Agg, semantic_model, semantic_view
from nxd.spec.data_types import number, string
from nxd.spec import dimension, field, metric, metric_field, primary_key

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
                number(),
                dimension(name="amount"),
                description="Deal amount, as reported by the source.",
            ),
            "updated_at": field(
                string(),
                dimension(name="updated_at"),
                description=(
                    "Last-updated timestamp reported by the source, carried "
                    "through unchanged as the source's ISO 8601 string."
                ),
            ),
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
            number(),
            metric(Agg.SUM, of=deals.field("amount"), name="total_amount"),
            description="Total amount across current (non-deleted) deals.",
        ),
    }
)

nxd_decisions = (
    semantic_model("nxd_decisions")
    .description(
        "Ledger of the rulings this data product materializes: the "
        "current-deal definition, the owner/email redaction, and the "
        "decision not to compute an attention ranking."
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

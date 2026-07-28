# suite.py — logistics-demo eval suite
#
# Covers the `shipments` semantic DP. Owned by the logistics platform team.
from nxd_eval import Case, Suite, checks, gold

GOLD = gold({
    "g_shipments_total": gold.rows("g_shipments_total", [
        {"shipment_count": 4820},
    ]),
    "g_shipments_by_carrier": gold.rows("g_shipments_by_carrier", [
        {"carrier": "NORTHWIND", "shipment_count": 2104, "freight_cost_usd": 388420.0},
        {"carrier": "PACIFICA", "shipment_count": 1655, "freight_cost_usd": 301775.5},
        {"carrier": "MERIDIAN", "shipment_count": 1061, "freight_cost_usd": 190330.0},
    ]),
    "g_late_by_lane": gold.rows("g_late_by_lane", [
        {"lane": "SEA-LAX", "late_shipment_count": 118},
        {"lane": "SEA-ORD", "late_shipment_count": 94},
        {"lane": "LAX-DFW", "late_shipment_count": 61},
    ]),
})

CHECKS = checks(
    clarify=[
        "For 'worst carrier', the agent asks whether worst means the most late "
        "shipments or the highest freight cost rather than silently picking one.",
    ],
    abstain=[
        "There is no fuel-surcharge metric in describe_model; the agent says so "
        "and does not derive one from freight_cost_usd.",
    ],
)

SUITE = Suite(
    name="logistics-demo",
    cases=[
        Case(
            id="q1-total-shipments",
            question="How many shipments are there in total?",
            expect="answer",
            gold_id="g_shipments_total",
            metadata={"why": "single metric, no dimension, no join"},
        ),
        Case(
            id="q2-by-carrier",
            question="Break down shipment count and total freight cost by carrier.",
            expect="answer",
            gold_id="g_shipments_by_carrier",
            metadata={"why": "two measures by one dimension; name-aware gold"},
        ),
        Case(
            id="q3-late-by-lane",
            question="How many late shipments were there on each lane?",
            expect="answer",
            gold_id="g_late_by_lane",
            metadata={"why": "boolean-flag metric sliced by a dimension"},
        ),
        Case(
            id="q4-worst-carrier",
            question="Which carrier is worst?",
            expect="clarify",
            metadata={"why": "'worst' is ambiguous: late count vs freight cost"},
        ),
        Case(
            id="q5-fuel-surcharge",
            question="What is the fuel surcharge by carrier?",
            expect="abstain",
            metadata={"why": "no fuel-surcharge metric exists in the catalog"},
        ),
    ],
    gold=GOLD,
    checks=CHECKS,
)

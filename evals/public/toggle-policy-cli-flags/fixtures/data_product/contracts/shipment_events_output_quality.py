"""Great Expectations contract for the curated shipment events output port."""


def validate(context):
    df = context.read_output("curated_shipment_events")

    context.expect(df["CARRIER_CODE"].notnull().all(), "CARRIER_CODE must be non-null")
    context.expect(df["SHIPPED_AT"].notnull().all(), "SHIPPED_AT must be non-null")
    context.expect(
        df["SHIPPED_AT"].max() >= context.now() - context.hours(6),
        "curated shipment events must be no more than 6 hours stale",
    )
    return context.result()

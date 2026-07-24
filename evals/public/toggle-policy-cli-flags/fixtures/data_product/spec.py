from nxd.spec import (
    code,
    data_product,
    data_product_output,
    quality,
    schedule,
    script,
    semantic_model,
    source_aligned_input,
    storage,
)

import transform
from models import shipment_event

SERVICE = "/infra-profile/logistics-demo-infra-profile#/services/snowflake-warehouse"

dp = (
    data_product("shipment-events-curated")
    .description("Curated carrier shipment events for the demo tenant.")
    .domain("Logistics")
    .input(
        source_aligned_input("raw_shipment_events")
        .service(SERVICE)
        .model(shipment_event)
    )
    .output(
        data_product_output("curated_shipment_events")
        .storage(storage(SERVICE).table("CURATED_SHIPMENT_EVENTS"))
        .promise(quality("gx", "contracts/shipment_events_output_quality.py"))
    )
    .transform(
        script(code(transform)).schedule(schedule.cron("0 * * * *"))
    )
)

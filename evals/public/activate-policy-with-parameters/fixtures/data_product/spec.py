from nxd.spec import (
    code,
    data_product,
    data_product_output,
    script,
    source_aligned_input,
    storage,
)

import transform
from models import customer_profile

raw_profiles = source_aligned_input("raw_profiles").service(
    "/infra-profile/acme-prod/#/services/snowflake-warehouse"
)

curated = data_product_output("curated").promise(customer_profile).storage(
    storage("/infra-profile/acme-prod/#/services/snowflake-warehouse")
    .database("ANALYTICS")
    .schema("CUSTOMER")
    .table("CUSTOMER_PROFILES_CURATED")
)

dp = (
    data_product("customer-profiles-curated")
    .domain("Customer")
    .inputs(raw_profiles)
    .outputs(curated)
    .transform(script(code(transform)).schedule("0 3 * * *"))
)

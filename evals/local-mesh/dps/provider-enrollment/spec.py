"""Deployable semantic DP backing the local mesh filter-coverage eval."""

from nxd.spec import code, data_product, data_product_output, storage
from transform import transform
from models import enrollment_metrics, patient_enrollment, patient_provider, provision_marker


INFRA_PROFILE = "ecommerce-demo"

_storage = (
    data_product_output()
    .promise(provision_marker)
    .promise(patient_enrollment)
    .promise(patient_provider)
    .model(enrollment_metrics)
    .port(
        "snowflake",
        storage(f"/infra-profile/{INFRA_PROFILE}#/services/nxd-snowflake"),
    )
)

spec = (
    data_product(
        name="eval-provider-enrollment",
        domain="analytics",
        description=(
            "Synthetic provider enrollment facts for the public semantic filter "
            "coverage eval. All rows and identifiers are generated fixtures."
        ),
        version="0.1.0-dev",
        infra_profile=INFRA_PROFILE,
    )
    .transform(
        code(transform).compute(
            f"/infra-profile/{INFRA_PROFILE}#/services/k8s-compute"
        )
    )
    .output(_storage)
    .semantic_tools(service="mcp-api-service-k8s")
)

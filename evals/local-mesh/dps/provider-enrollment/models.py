"""Synthetic patient enrollment fact and unique provider dimension."""

from nxd.spec import (
    Agg,
    Cardinality,
    FilterOp,
    FilterSpec,
    dimension,
    field,
    join,
    metric,
    metric_field,
    primary_key,
    semantic_model,
    semantic_view,
)
from nxd.spec.data_types import boolean, date, int64, string


patient_provider = (
    semantic_model("patient_provider")
    .description(
        "One row per synthetic patient with the patient's treating provider "
        "attributes. Keyed by patient so distinct-patient metrics can join "
        "through the patient key."
    )
    .fields(
        {
            "PATIENT_ID": field(string(), primary_key()),
            "NPI": field(
                string(),
                description="Synthetic treating-provider identifier.",
            ),
            "SPECIALTY_GROUP": field(
                string(),
                dimension(name="specialty_group"),
                description="Synthetic specialty group of the patient's provider.",
            ),
            "TERRITORY": field(
                string(),
                dimension(name="territory"),
                description="Synthetic territory label of the patient's provider.",
            ),
        }
    )
)

patient_enrollment = (
    semantic_model("patient_enrollment")
    .description(
        "Enrollment fact grain: one patient, product, and reporting period. "
        "Patients can have multiple products and period rows."
    )
    .fields(
        {
            "ENROLLMENT_ID": field(int64(), primary_key()),
            "PATIENT_ID": field(
                string(),
                dimension(name="patient_id", pii=True),
                join(
                    to="patient_provider",
                    to_column="PATIENT_ID",
                    cardinality=Cardinality.MANY_TO_ONE,
                ),
                description="Synthetic patient identifier; not a real person.",
            ),
            "PRODUCT_NAME": field(
                string(),
                dimension(name="product_name"),
                description="Synthetic product label; ALL is the rollup row.",
            ),
            "REGION_NAME": field(
                string(),
                dimension(name="region_name"),
                description="Organization-prefixed synthetic region label.",
            ),
            "NPI": field(string(), description="Synthetic provider identifier."),
            "PERIOD_TYPE": field(
                string(),
                dimension(name="period_type"),
                description="Reporting period type (DAILY or WEEKLY).",
            ),
            "ENROLLMENT_DATE": field(
                date(),
                dimension(name="enrollment_date"),
                description="Synthetic enrollment date.",
            ),
            "FIRST_ENROLLMENT_FLAG": field(
                boolean(),
                dimension(name="first_enrollment_flag"),
                description="Whether this row represents a first enrollment.",
            ),
            "REFILLS": field(int64(), description="Synthetic refill count."),
        }
    )
)

_daily_only = FilterSpec(
    field=patient_enrollment.field("PERIOD_TYPE"),
    op=FilterOp.EQ,
    value="DAILY",
)

enrollment_metrics = (
    semantic_view("enrollment_metrics", patient_enrollment)
    .description("Governed enrollment metrics over patient_enrollment.")
    .fields(
        {
            "ENROLLED_PATIENTS": metric_field(
                int64(),
                metric(
                    Agg.COUNT_DISTINCT,
                    of=patient_enrollment.field("PATIENT_ID"),
                    filters=[_daily_only],
                ),
                description=(
                    "Distinct patients with a DAILY enrollment row. The DAILY "
                    "period filter is part of this metric's definition."
                ),
            ),
            "ENROLLMENT_ROWS": metric_field(
                int64(),
                metric(Agg.COUNT, of=patient_enrollment.field("*")),
                description="Count of fact rows across all reporting periods.",
            ),
            "REFILL_COUNT": metric_field(
                int64(),
                metric(Agg.SUM, of=patient_enrollment.field("REFILLS")),
                description="Sum of synthetic refill counts across fact rows.",
            ),
        }
    )
)

provision_marker = (
    semantic_model("eval_enrollment_marker")
    .description("One-row marker produced by the enrollment fixture transform.")
    .schema({"MARKER_ID": int64(), "MARKER_VALUE": string()})
)

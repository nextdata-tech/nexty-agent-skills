"""Seed deterministic, fully synthetic fact and dimension tables."""

from datetime import date, timedelta

from nxd.data_product.context import Snowflake


# Product and region labels are fabricated for this public fixture. Provider
# values are deliberately not numeric NPIs and cannot identify real clinicians.
_PROVIDERS = [
    ("SYNTH-NPI-101", "Psychiatry & Neurology", "Territory North"),
    ("SYNTH-NPI-102", "Neurology", "Territory Central"),
    ("SYNTH-NPI-103", "Rheumatology", "Territory West"),
    ("SYNTH-NPI-104", "Internal Medicine", "Territory Central"),
]

# patient_id, region, provider key, products. Each DAILY fact has an ALL rollup.
_PATIENTS = [
    ("P001", "NE Gulf Coast", "SYNTH-NPI-101", ("ALPHAVIR",)),
    ("P002", "NE Gulf Coast", "SYNTH-NPI-101", ("ALPHAVIR", "BETAMAB")),
    ("P003", "NE Gulf Coast", "SYNTH-NPI-101", ("ALPHAVIR SC",)),
    ("P004", "NE Gulf Coast", "SYNTH-NPI-102", ("ALPHAVIR SC",)),
    ("P005", "NE Gulf Coast", "SYNTH-NPI-102", ("BETAMAB",)),
    ("P006", "NE Gulf Coast", "SYNTH-NPI-102", ("ALPHAVIR",)),
    ("P007", "NE Gulf Coast", "SYNTH-NPI-102", ("BETAMAB",)),
    ("P008", "NE Great Lakes", "SYNTH-NPI-101", ("ALPHAVIR",)),
    ("P009", "NE Great Lakes", "SYNTH-NPI-101", ("BETAMAB",)),
    ("P010", "NE Great Lakes", "SYNTH-NPI-102", ("ALPHAVIR",)),
    ("P011", "NE Great Lakes", "SYNTH-NPI-102", ("BETAMAB",)),
    ("P012", "NE Great Lakes", "SYNTH-NPI-103", ("ALPHAVIR",)),
    ("P013", "NE Great Lakes", "SYNTH-NPI-104", ("BETAMAB",)),
    ("P016", "SW Desert", "SYNTH-NPI-101", ("ALPHAVIR SC",)),
    ("P017", "SW Desert", "SYNTH-NPI-102", ("ALPHAVIR",)),
    ("P018", "SW Desert", "SYNTH-NPI-103", ("ALPHAVIR SC",)),
    ("P019", "SW Desert", "SYNTH-NPI-104", ("ALPHAVIR",)),
    ("P020", "NE Great Lakes", "SYNTH-NPI-101", ("ALPHAVIR",)),
    ("P021", "NE Great Lakes", "SYNTH-NPI-101", ("BETAMAB",)),
    ("P022", "NE Great Lakes", "SYNTH-NPI-101", ("ALPHAVIR SC",)),
    ("P023", "NE Great Lakes", "SYNTH-NPI-102", ("ALPHAVIR SC",)),
]

# These synthetic people occur only in weekly facts. They prove the DAILY
# definition filter changes the metric result even though COUNT DISTINCT is used.
_WEEKLY_ONLY = [
    ("P024", "NE Gulf Coast", "SYNTH-NPI-101", "ALPHAVIR"),
    ("P025", "NE Gulf Coast", "SYNTH-NPI-101", "ALPHAVIR SC"),
    ("P026", "NE Gulf Coast", "SYNTH-NPI-101", "BETAMAB"),
]


def _patient_providers() -> list[tuple]:
    """One row per patient: PATIENT_ID, NPI, SPECIALTY_GROUP, TERRITORY."""
    by_npi = {npi: (specialty, territory) for npi, specialty, territory in _PROVIDERS}
    patients = [(pid, npi) for pid, _region, npi, _products in _PATIENTS]
    patients += [(pid, npi) for pid, _region, npi, _product in _WEEKLY_ONLY]
    return [(pid, npi, *by_npi[npi]) for pid, npi in sorted(patients)]


def _build_rows() -> list[tuple]:
    rows: list[tuple] = []
    enrollment_id = 1
    start = date(2026, 1, 1)

    def add(patient_id, product, region, npi, period, day_number, first, refills):
        nonlocal enrollment_id
        rows.append(
            (
                enrollment_id,
                patient_id,
                product,
                region,
                npi,
                period,
                start + timedelta(days=day_number),
                first,
                refills,
            )
        )
        enrollment_id += 1

    for index, (patient_id, region, npi, products) in enumerate(_PATIENTS):
        day_number = index % 25
        total_refills = 0
        for product_index, product in enumerate(products):
            refills = (index + product_index) % 4
            total_refills += refills
            add(
                patient_id,
                product,
                region,
                npi,
                "DAILY",
                day_number,
                product_index == 0,
                refills,
            )
        add(patient_id, "ALL", region, npi, "DAILY", day_number, True, total_refills)

    # A small number of ordinary patients also have WEEKLY rows; repeated
    # periods do not increase the daily distinct count.
    for day_number, (patient_id, region, npi, product) in enumerate(
        [
            ("P001", "NE Gulf Coast", "SYNTH-NPI-101", "ALPHAVIR"),
            ("P008", "NE Great Lakes", "SYNTH-NPI-101", "ALPHAVIR"),
        ],
        start=26,
    ):
        add(patient_id, product, region, npi, "WEEKLY", day_number, False, 1)
        add(patient_id, "ALL", region, npi, "WEEKLY", day_number, False, 1)

    for index, (patient_id, region, npi, product) in enumerate(_WEEKLY_ONLY, start=28):
        add(patient_id, product, region, npi, "WEEKLY", index, True, index % 3)
        add(patient_id, "ALL", region, npi, "WEEKLY", index, True, index % 3)
    return rows


def transform(snowflake: Snowflake) -> None:
    from snowflake import connector

    if snowflake is None or not snowflake.schema:
        print("LOCAL_MESH_EVAL skipped — no Snowflake schema in context")
        return

    # Promotion is on by default: the platform provisions a staging table per
    # promised model and swaps it in after the run, so the transform must write
    # to full_table_name(<model>), not to the final table name.
    providers_table = snowflake.full_table_name("patient_provider")
    patients_table = snowflake.full_table_name("patient_enrollment")
    conn = connector.connect(
        user=snowflake.user,
        account=snowflake.account,
        warehouse=snowflake.warehouse,
        role=snowflake.role,
        database=snowflake.database,
        schema=snowflake.schema,
        ocsp_fail_open=True,
        **snowflake.connector_params(),
    )
    try:
        cur = conn.cursor()
        try:
            cur.execute(f"TRUNCATE TABLE IF EXISTS {providers_table}")
            cur.executemany(
                f"INSERT INTO {providers_table} VALUES (%s, %s, %s, %s)",
                _patient_providers(),
            )
            cur.execute(f"TRUNCATE TABLE IF EXISTS {patients_table}")
            rows = _build_rows()
            cur.executemany(
                f"INSERT INTO {patients_table} VALUES "
                "(%s, %s, %s, %s, %s, %s, %s, %s, %s)",
                rows,
            )
            marker = snowflake.full_table_name("eval_enrollment_marker")
            cur.execute(f"TRUNCATE TABLE IF EXISTS {marker}")
            cur.execute(
                f"INSERT INTO {marker} (MARKER_ID, MARKER_VALUE) VALUES (%s, %s)",
                (1, "provider-enrollment-eval"),
            )
            print(
                "LOCAL_MESH_EVAL seeded synthetic rows: "
                f"patient_enrollment={len(rows)}, patient_provider={len(_patient_providers())}"
            )
        finally:
            cur.close()
    finally:
        conn.close()

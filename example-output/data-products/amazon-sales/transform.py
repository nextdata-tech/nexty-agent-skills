"""Amazon-sales transform: S3 CSV -> Snowflake table.

Read `check-state/demo/amazon-sales.csv` from the daff-s3 bucket, normalise
the `date-shipped` column header to `date_shipped`, and bulk-insert rows
into the daff Snowflake `CHECK_POSTFIX_STAGING.AMAZON_SALES` table.
"""

from __future__ import annotations

import io
import logging
from datetime import date as _date

import boto3
import pandas as pd
from nxd.data_product.context import S3Input, Snowflake
from snowflake.connector import connect

_logger = logging.getLogger("transform.amazon_sales")
_logger.setLevel(logging.INFO)


_INPUT_MODEL_NAME = "amazon_sales"
_DEFAULT_INPUT_KEY = "check-state/demo/amazon-sales.csv"
_OUTPUT_TABLE = "AMAZON_SALES"


def _resolve_input_key(s3_input: S3Input) -> str:
    """The S3 object key for the input model.

    nxd's `S3Input` exposes per-model paths via `model_output_paths` /
    `model_urls`; fall back to the declared spec path if neither is wired
    through by the runtime. TODO: verify against runtime contract.
    """
    paths = getattr(s3_input, "model_output_paths", None) or {}
    if _INPUT_MODEL_NAME in paths:
        return paths[_INPUT_MODEL_NAME]
    urls = getattr(s3_input, "model_urls", None) or {}
    if _INPUT_MODEL_NAME in urls:
        return urls[_INPUT_MODEL_NAME]
    return _DEFAULT_INPUT_KEY


def _read_csv_from_s3(s3_input: S3Input) -> pd.DataFrame:
    key = _resolve_input_key(s3_input)
    _logger.info("Reading s3://%s/%s", s3_input.bucket, key)
    s3 = boto3.client("s3")
    body = s3.get_object(Bucket=s3_input.bucket, Key=key)["Body"].read()
    df = pd.read_csv(io.BytesIO(body))
    # The CSV header carries `date-shipped`; the model uses snake_case.
    df = df.rename(columns={"date-shipped": "date_shipped"})
    df["date_shipped"] = pd.to_datetime(df["date_shipped"], errors="coerce").dt.date
    return df[["asin", "date_shipped"]]


def _write_to_snowflake(snowflake: Snowflake, df: pd.DataFrame) -> int:
    table = snowflake.model_tables.get(_INPUT_MODEL_NAME, _OUTPUT_TABLE)
    schema = snowflake.schema
    _logger.info(
        "Writing %d rows to %s.%s.%s",
        len(df),
        snowflake.database,
        schema,
        table,
    )

    conn = connect(
        user=snowflake.user,
        password=snowflake.password,
        account=snowflake.account,
        warehouse=snowflake.warehouse,
        database=snowflake.database,
        schema=schema,
        role=snowflake.role,
    )
    try:
        cur = conn.cursor()
        try:
            cur.execute(f"TRUNCATE TABLE IF EXISTS {schema}.{table}")
            cur.executemany(
                f"INSERT INTO {schema}.{table} (ASIN, DATE_SHIPPED) "
                f"VALUES (%s, %s::DATE)",
                [
                    (
                        row["asin"],
                        row["date_shipped"].isoformat()
                        if isinstance(row["date_shipped"], _date)
                        else None,
                    )
                    for _, row in df.iterrows()
                ],
            )
            conn.commit()
        finally:
            cur.close()
    finally:
        conn.close()
    return len(df)


def transform(s3_source: S3Input, snowflake: Snowflake) -> None:
    """Entrypoint bound by spec.py: input port `s3-source` -> output port
    `snowflake`. Parameter names match the port names with hyphens replaced
    by underscores."""
    df = _read_csv_from_s3(s3_source)
    n = _write_to_snowflake(snowflake, df)
    _logger.info("amazon-sales transform complete — %d rows loaded", n)

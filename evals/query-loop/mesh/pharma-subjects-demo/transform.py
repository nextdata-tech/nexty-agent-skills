"""Transform for pharma-subjects-demo — a deliberate NO-OP.

All seeding (marker, base table, single-table semantic view) happens at PROVISION
time in provision.py (`@on_provision`), because the kernel verifies output-port
promises BEFORE the transform. This `.transform()` exists ONLY so the `**/*.py`
bundling glob ships registry.py / tools.py into the image (constraint #2) — the
rpc tool scripts import them at runtime.

It MUST do no Snowflake work: re-running the full seed here is redundant with
provision AND, when it errors/times out, fails the compute task -> the DP flaps
to State=Failed and the proxy 404s the rpc route. Keep it a pure no-op.
"""

from nxd.data_product.context import Snowflake


def transform(snowflake: Snowflake) -> None:
    # No-op: provisioning owns all seeding. See module docstring.
    print("SUBJECTS_DIAG transform no-op (seeding done at provision time)")

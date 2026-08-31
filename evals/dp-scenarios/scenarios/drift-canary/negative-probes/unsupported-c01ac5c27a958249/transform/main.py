"""Minimal valid transform for the unsupported-construction probe."""

from nxd import data_product


@data_product.on_transform()
def ingest(duckdb, secrets):
    return None


if __name__ == "__main__":
    data_product.main()

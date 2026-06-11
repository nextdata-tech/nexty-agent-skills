"""Shim re-exporting the nxd symbols `spec.py` uses via `from nxd_spec import *`.

Pulls in the project's own models and `transform` function so they're
available at spec-evaluation time, then re-exports every spec-builder
name through ``__all__``.
"""

from models import jira_issue, jira_issue_embeddings
from nxd.spec import (
    code,
    custom,
    data_product,
    data_product_access,
    data_product_output,
    owner,
    pg_vector_config,
    source_aligned_input,
    storage,
)
from nxd.spec.conditions import scheduled
from transform import transform
import api_source_freshness

__all__ = [
    "api_source_freshness",
    "code",
    "custom",
    "data_product",
    "data_product_access",
    "data_product_output",
    "jira_issue",
    "jira_issue_embeddings",
    "owner",
    "pg_vector_config",
    "scheduled",
    "source_aligned_input",
    "storage",
    "transform",
]

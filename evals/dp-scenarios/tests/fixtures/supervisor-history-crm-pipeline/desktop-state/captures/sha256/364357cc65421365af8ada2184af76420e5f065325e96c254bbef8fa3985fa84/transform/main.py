"""crm-pipeline: fetch current CRM deals over the api-source REST API and
land the governed, redacted result into the local DuckDB output port."""

from __future__ import annotations

import csv
import json
import math
import os
import time
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Iterator
from urllib.parse import urljoin, urlsplit

import dlt
import requests
from dlt.sources.rest_api import rest_api_resources, RESTAPIConfig

from nxd import data_product
from nxd.core.context import DuckDbOutput

# Landed tables exposed by spec.py; never semantic views.
# `deals` is fetched over HTTP (API_MODELS); `nxd_decisions` is landed
# reference data this closure authors itself (BASE_MODELS). Neither has a
# connector-owned data/ export in the API_MODELS case; nxd_decisions does,
# at data/nxd_decisions/nxd_decisions.csv.
API_MODELS = ("deals",)
BASE_MODELS = ("nxd_decisions",)
DERIVED_MODELS: tuple[str, ...] = ()
PHYSICAL_MODELS = ("deals", "nxd_decisions")
OPTIONAL_EMPTY_MODELS: tuple[str, ...] = ()
assert set(PHYSICAL_MODELS) == set(API_MODELS + BASE_MODELS + DERIVED_MODELS)


# ---------------------------------------------------------------------------
# Refresh-aware requests session, adapted from the shipped source recipe
# (nxd-generate-data-product/scripts/api_source_refresh_session.py), copied
# into this self-contained transform per that recipe's own instruction.
# Parameterized on auth_header / auth_scheme because this profile's
# generic-secrets attributes name them explicitly rather than assuming the
# `bearer` auth_type convention.
# ---------------------------------------------------------------------------


def _headers_from(secrets: Mapping[str, Any]) -> dict[str, str]:
    """Rebuild non-secret flat header attributes exactly once per config."""
    headers = {}
    for key, value in secrets.items():
        if not key.startswith("header_") or value in (None, ""):
            continue
        name = "-".join(part.title() for part in key[len("header_"):].split("_"))
        if name.lower() == "authorization":
            raise ValueError("caller-supplied Authorization header is not allowed")
        headers[name] = str(value)
    return headers


class RefreshingSession(requests.Session):
    """Replay one request safely after one refresh or one rate-limit response."""

    _TOKEN_FIELDS = (
        "token",
        "access_token",
        "bearer_token",
        "new_token",
        "accessToken",
        "bearerToken",
    )

    def __init__(
        self,
        *,
        base_url: str,
        auth_refresh_path: str,
        auth_token: str,
        auth_header: str = "Authorization",
        auth_scheme: str = "Bearer",
        headers: Mapping[str, str] | None = None,
        timeout_s: float = 30.0,
        max_retry_after_s: float = 30.0,
    ) -> None:
        super().__init__()
        self._base_url = self._validate_base_url(base_url)
        self._refresh_url = self._resolve_refresh_url(self._base_url, auth_refresh_path)
        if not isinstance(auth_token, str) or not auth_token.strip():
            raise ValueError("auth_token must be a non-empty string")
        if not math.isfinite(timeout_s) or timeout_s <= 0:
            raise ValueError("timeout_s must be finite and positive")
        if not math.isfinite(max_retry_after_s) or max_retry_after_s <= 0:
            raise ValueError("max_retry_after_s must be finite and positive")
        self._token = auth_token
        self._auth_header = auth_header
        self._auth_scheme = auth_scheme
        self._custom_headers = self._merge_headers(headers or {})
        self._timeout_s = float(timeout_s)
        self._max_retry_after_s = float(max_retry_after_s)

    @staticmethod
    def _origin(url: str) -> tuple[str, str, int | None]:
        try:
            parsed = urlsplit(url)
            hostname = parsed.hostname
            port = parsed.port
        except ValueError:
            raise ValueError("URL must have a valid HTTP(S) origin") from None
        if parsed.scheme.lower() not in {"http", "https"} or hostname is None:
            raise ValueError("URL must have a valid HTTP(S) origin")
        if parsed.username is not None or parsed.password is not None:
            raise ValueError("URL must not contain credentials")
        return parsed.scheme.lower(), hostname.lower(), port

    @classmethod
    def _validate_base_url(cls, base_url: str) -> str:
        if not isinstance(base_url, str) or not base_url.strip():
            raise ValueError("base_url must be a non-empty URL")
        cls._origin(base_url)
        parsed = urlsplit(base_url)
        if parsed.query or parsed.fragment:
            raise ValueError("base_url must not contain a query or fragment")
        return base_url.rstrip("/") + "/"

    @classmethod
    def _resolve_refresh_url(cls, base_url: str, auth_refresh_path: str) -> str:
        if not isinstance(auth_refresh_path, str) or not auth_refresh_path.strip():
            raise ValueError("auth_refresh_path must be a same-origin path")
        try:
            path = urlsplit(auth_refresh_path)
        except ValueError:
            raise ValueError("auth_refresh_path must be a same-origin path") from None
        if path.scheme or path.netloc or auth_refresh_path.startswith("//") or path.query or path.fragment:
            raise ValueError("auth_refresh_path must be a same-origin path without query data")
        resolved = urljoin(base_url, auth_refresh_path)
        if cls._origin(resolved) != cls._origin(base_url):
            raise ValueError("auth_refresh_path must resolve to base_url origin")
        return resolved

    @staticmethod
    def _replay_plan(request):
        body = request.body
        if body is None or isinstance(body, (bytes, bytearray, memoryview, str)):
            return lambda: None
        tell = getattr(body, "tell", None)
        seek = getattr(body, "seek", None)
        if not callable(tell) or not callable(seek):
            raise TypeError("request body must be replayable for an authenticated retry")
        try:
            position = tell()
            seek(position)
        except (OSError, TypeError, ValueError):
            raise TypeError("request body must be replayable for an authenticated retry") from None

        def rewind() -> None:
            try:
                seek(position)
            except (OSError, TypeError, ValueError):
                raise TypeError("request body could not be rewound for replay") from None

        return rewind

    @staticmethod
    def _retry_delay(retry_after: str | None, maximum: float) -> float:
        if retry_after is None:
            return min(1.0, maximum)
        try:
            delay = float(retry_after)
        except (TypeError, ValueError):
            return 0.0
        if math.isnan(delay) or delay < 0:
            return 0.0
        if math.isinf(delay):
            return maximum if delay > 0 else 0.0
        return min(delay, maximum)

    @staticmethod
    def _merge_headers(*header_maps: Mapping[str, str]) -> dict[str, str]:
        merged: dict[str, str] = {}
        for header_map in header_maps:
            for name, value in header_map.items():
                if not isinstance(name, str):
                    raise TypeError("request headers must use string names")
                if name.lower() == "authorization":
                    raise ValueError("caller-supplied Authorization header is not allowed")
                for existing in list(merged):
                    if existing.lower() == name.lower():
                        del merged[existing]
                merged[name] = str(value)
        return merged

    @staticmethod
    def _set_header(headers: dict[str, str], name: str, value: str) -> None:
        for existing in list(headers):
            if existing.lower() == name.lower():
                del headers[existing]
        headers[name] = value

    def _refresh_token(self, timeout: float) -> str:
        refresh_headers = self._merge_headers({"Accept": "application/json"}, self._custom_headers)
        self._set_header(refresh_headers, self._auth_header, f"{self._auth_scheme} {self._token}")
        refresh_request = requests.Request("POST", self._refresh_url, headers=refresh_headers).prepare()
        try:
            response = super().send(refresh_request, timeout=timeout, allow_redirects=False)
        except Exception:
            raise RuntimeError("token refresh request failed") from None
        try:
            if not 200 <= response.status_code < 300:
                raise RuntimeError("token refresh returned a non-2xx status")
            try:
                payload = response.json()
            except (ValueError, json.JSONDecodeError):
                raise RuntimeError("token refresh returned invalid JSON") from None
            if not isinstance(payload, Mapping):
                raise RuntimeError("token refresh JSON must be an object")
            present = [(field, payload[field]) for field in self._TOKEN_FIELDS if field in payload]
            if not present:
                return self._token
            for field, value in present:
                if not isinstance(value, str) or not value.strip():
                    raise RuntimeError(f"token refresh field {field} must be a non-empty string")
            values = {value.strip() for _, value in present}
            if len(values) != 1:
                raise RuntimeError("token refresh fields contain conflicting values")
            return values.pop()
        finally:
            response.close()

    def send(self, request, **kwargs):
        if self._origin(request.url) != self._origin(self._base_url):
            raise ValueError("request URL must be same-origin with base_url")
        rewind = self._replay_plan(request)
        request.headers = self._merge_headers(request.headers, self._custom_headers)
        timeout = kwargs.get("timeout", self._timeout_s)
        if timeout is None or not isinstance(timeout, (int, float)) or timeout <= 0:
            raise ValueError("timeout must be a positive number")
        send_kwargs = dict(kwargs)
        send_kwargs["timeout"] = timeout
        send_kwargs["allow_redirects"] = False
        refreshed = False
        rate_retried = False
        while True:
            self._set_header(request.headers, self._auth_header, f"{self._auth_scheme} {self._token}")
            hook_error = None
            try:
                response = super().send(request, **send_kwargs)
            except requests.exceptions.HTTPError as error:
                response = getattr(error, "response", None)
                if response is None:
                    raise
                status_code = getattr(response, "status_code", None)
                if status_code not in {401, 429}:
                    raise
                hook_error = error
            else:
                status_code = response.status_code

            if status_code == 401:
                if refreshed:
                    response.close()
                    raise RuntimeError("request remained unauthorized after one refresh")
                response.close()
                self._token = self._refresh_token(timeout)
                refreshed = True
                rewind()
                continue
            if status_code == 429 and not rate_retried:
                delay = self._retry_delay(response.headers.get("Retry-After"), self._max_retry_after_s)
                response.close()
                time.sleep(delay)
                rate_retried = True
                rewind()
                continue
            if hook_error is not None:
                response.close()
                raise hook_error
            if status_code in (401, 429):
                # Retries for this status are exhausted (one refresh, one
                # rate-limit wait). Raise instead of returning the failed
                # response as if it were ordinary -- an unrecognized
                # passthrough here could truncate pagination silently.
                response.close()
                raise RuntimeError(
                    f"request failed with status {status_code} after "
                    f"exhausting the bounded retry budget for this request"
                )
            return response


def _maybe_parsed(value: Any) -> Any:
    """This profile's generic-secrets attributes may arrive already
    structured (list/dict/int) or JSON-encoded as a string, depending on
    how the supervisor's driver preserves YAML attribute types. Accept
    either."""
    if isinstance(value, str):
        try:
            return json.loads(value)
        except (TypeError, ValueError):
            return value
    return value


# ---------------------------------------------------------------------------


@data_product.on_transform()
def ingest(duckdb: DuckDbOutput, secrets: dict[str, Any]) -> None:
    """Land the current CRM deals plus the decisions ledger into DuckDB."""
    run_dir = Path(duckdb.path).parent
    pipelines_dir = run_dir / "dlt-pipelines"
    pipelines_dir.mkdir(parents=True, exist_ok=True)
    os.environ["DLT_DATA_DIR"] = str(run_dir / "dlt-data")

    pipeline = dlt.pipeline(
        pipelines_dir=str(pipelines_dir),
        destination=dlt.destinations.duckdb(credentials=duckdb.path),
        dataset_name=duckdb.schema,
    )

    # --- Fetched source: current CRM deals -------------------------------
    base_url = secrets["base_url"]
    auth_header_name = secrets.get("auth_header", "Authorization")
    auth_scheme = secrets.get("auth_scheme", "Bearer")
    credential_env = secrets.get("credential_env")
    auth_refresh_path = secrets.get("auth_refresh_path")

    if not credential_env:
        raise ValueError(
            "api-source secrets missing 'credential_env' -- the attribute "
            "naming the environment variable that carries the live bearer "
            "token is required by this profile"
        )
    auth_token = os.environ.get(credential_env)
    if not auth_token:
        raise RuntimeError(
            f"environment variable {credential_env!r} named by the "
            f"api-source credential_env attribute is not set at transform "
            f"run time"
        )
    if not auth_refresh_path:
        raise ValueError("api-source secrets missing 'auth_refresh_path' for this bearer flow")

    headers = _headers_from(secrets)
    session = RefreshingSession(
        base_url=base_url,
        auth_refresh_path=auth_refresh_path,
        auth_token=auth_token,
        auth_header=auth_header_name,
        auth_scheme=auth_scheme,
        headers=headers,
    )
    client_config: dict[str, Any] = {"base_url": base_url, "session": session}
    if headers:
        client_config["headers"] = headers

    pagination = _maybe_parsed(secrets.get("endpoint_deals_pagination")) or {}
    cursor_field = pagination.get("cursor_field", "next_cursor")
    cursor_param = pagination.get("cursor_param", "cursor")
    data_selector = secrets.get("endpoint_deals_data_selector", "data")

    config: RESTAPIConfig = {
        "client": client_config,
        "resources": [
            {
                "name": "deals",
                "endpoint": {
                    "path": secrets["endpoint_deals"],
                    "data_selector": data_selector,
                    "paginator": {
                        "type": "cursor",
                        "cursor_path": cursor_field,
                        "cursor_param": cursor_param,
                    },
                },
            }
        ],
    }
    api_resources = {r.name: r for r in rest_api_resources(config)}

    # Counted here, synchronously, as rows stream through the filter --
    # this is the run's own independent tally of what the source reported,
    # captured before the status value is ever discarded. It becomes the
    # "current-deals-non-deleted" contract's witness below: that verifier
    # has no landed status column to read (status is never landed at all,
    # per the approved blueprint), so it instead reconciles the landed
    # `deals` row count against this fetched-vs-excluded tally, recorded
    # into the nxd_decisions ledger once this run is known-complete.
    _counts = {"fetched": 0, "excluded_deleted": 0}

    def _is_current(record: dict[str, Any]) -> bool:
        _counts["fetched"] += 1
        if record.get("status") == "deleted":
            _counts["excluded_deleted"] += 1
            return False
        return True

    def _flatten_deal(record: dict[str, Any]) -> dict[str, Any]:
        """Flat scalars only, and only the governed columns: the deal
        name, the status field, and the whole owner object (name + email)
        are read from the source response here and never copied into the
        returned dict, so none of them are ever landed in any stored
        surface of this product."""
        return {
            "deal_id": str(record.get("id")),
            "stage": record.get("stage"),
            "amount": record.get("amount"),
            "updated_at": record.get("updatedAt"),
        }

    deals_reader = (
        api_resources["deals"]
        .add_filter(_is_current)
        .add_map(_flatten_deal)
        .with_name(duckdb.model_tables["deals"])
    )

    # Deals land in their own run first, so _counts is fully populated --
    # and the deals table itself fully written -- before the decisions
    # ledger below reads it. dlt does not guarantee one resource in a
    # shared `pipeline.run([...])` list is exhausted before another is
    # pulled, so this is a deliberate two-run split, not a merge of the
    # base reader loop with the reference-data resource.
    pipeline.run([deals_reader], write_disposition="replace")

    landed_deals = pipeline.default_schema.data_table_names()
    if duckdb.model_tables["deals"] not in landed_deals:
        raise RuntimeError(
            f"dlt did not produce the required 'deals' table; got {sorted(landed_deals)!r}"
        )
    with pipeline.sql_client() as client:
        landed_deal_count = client.execute_sql(
            f"SELECT COUNT(*) FROM {duckdb.model_tables['deals']}"
        )[0][0]
    expected_deal_count = _counts["fetched"] - _counts["excluded_deleted"]
    if landed_deal_count != expected_deal_count:
        raise RuntimeError(
            f"landed deal count {landed_deal_count} does not reconcile with "
            f"fetched ({_counts['fetched']}) minus excluded-deleted "
            f"({_counts['excluded_deleted']}) = {expected_deal_count}"
        )

    # --- Landed reference data: the decisions ledger --------------------
    # Anchor on the execution root, not the caller's cwd; the desktop
    # python-compute driver exports NXD_TRANSFORM_ROOT unconditionally.
    root = Path(os.environ["NXD_TRANSFORM_ROOT"])
    decision_rows: list[dict[str, str]] = []
    for path in sorted((root / "data" / "nxd_decisions").glob("*.csv")):
        with path.open(newline="", encoding="utf-8") as handle:
            decision_rows.extend(csv.DictReader(handle))

    for row in decision_rows:
        if row.get("decision_id") == "current-deal-definition":
            row["detail"] = (
                f"{row['detail']} Run evidence: fetched={_counts['fetched']}; "
                f"excluded_deleted={_counts['excluded_deleted']}; "
                f"landed={landed_deal_count}."
            )

    @dlt.resource(name=duckdb.model_tables["nxd_decisions"])
    def nxd_decisions_resource() -> Iterator[dict[str, Any]]:
        yield from decision_rows

    pipeline.run([nxd_decisions_resource()], write_disposition="replace")

    actual = set(pipeline.default_schema.data_table_names())
    expected = {duckdb.model_tables[model] for model in PHYSICAL_MODELS}
    optional = {duckdb.model_tables[model] for model in OPTIONAL_EMPTY_MODELS}
    missing = expected - actual
    absent_optional = missing & optional
    if actual != expected - absent_optional:
        raise RuntimeError(
            f"dlt produced tables {sorted(actual)!r}, expected required tables "
            f"{sorted(expected - optional)!r}; optional absent tables "
            f"{sorted(absent_optional)!r}; unexpected tables "
            f"{sorted(actual - expected)!r}"
        )
    (run_dir / ".transform-complete").touch()


if __name__ == "__main__":
    data_product.main()

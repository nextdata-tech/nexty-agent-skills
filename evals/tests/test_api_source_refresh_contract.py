"""Executable contract for the shipped expiring-credential api-source recipe.

The implementation under test is executed verbatim from the installed skill
script. The fake transport replaces ``requests.Session.send`` only, so these
tests do not make network requests and do not carry a second implementation of
the refresh state machine.
"""

from __future__ import annotations

import io
import json
import sys
import types
from pathlib import Path

import pytest

try:
    import requests as _real_requests
except ModuleNotFoundError:  # pragma: no cover - exercised by the standalone CI env
    _real_requests = None

REPO_ROOT = Path(__file__).resolve().parents[2]
API_SOURCE = (
    REPO_ROOT
    / "src"
    / "nxd-generate-data-product"
    / "reference"
    / "api-source.md"
)
REFRESH_SCRIPT = (
    REPO_ROOT
    / "src"
    / "nxd-generate-data-product"
    / "scripts"
    / "api_source_refresh_session.py"
)
BASE_URL = "https://api.example.test/v1/"
AUTH_REFRESH_PATH = "/auth/refresh"
REFRESH_URL = "https://api.example.test/auth/refresh"
SENSITIVE_TOKEN = "sensitive-test-token"


def _doc() -> str:
    return API_SOURCE.read_text(encoding="utf-8")


def _script_source() -> str:
    return REFRESH_SCRIPT.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def recipe_namespace() -> dict:
    """Execute the exact shipped script, including its imports."""
    namespace: dict = {}
    source = _script_source()
    if _real_requests is not None:
        exec(compile(source, "<api-source.md>", "exec"), namespace, namespace)
    else:
        # The standalone evals job intentionally installs only pytest, duckdb,
        # and pyyaml. Supply the tiny Request/Session protocol the extracted
        # recipe needs there; the real requests package is used whenever the
        # project environment provides it.
        class PreparedRequest:
            def __init__(self) -> None:
                self.method = None
                self.url = None
                self.headers = {}
                self.body = None

            def prepare(self, method, url, headers=None):
                self.method = method
                self.url = url
                self.headers = dict(headers or {})
                return self

        class Request:
            def __init__(self, method, url, headers=None) -> None:
                self.method = method
                self.url = url
                self.headers = headers

            def prepare(self):
                request = PreparedRequest()
                return request.prepare(self.method, self.url, self.headers)

        class Session:
            def __init__(self) -> None:
                pass

            def send(self, request, **kwargs):  # pragma: no cover - patched below
                raise AssertionError("the fake transport was not installed")

        fake_requests = types.ModuleType("requests")
        fake_requests.PreparedRequest = PreparedRequest
        fake_requests.Request = Request
        fake_requests.Session = Session
        previous = sys.modules.get("requests")
        sys.modules["requests"] = fake_requests
        try:
            exec(compile(source, "<api-source.md>", "exec"), namespace, namespace)
        finally:
            if previous is None:
                sys.modules.pop("requests", None)
            else:
                sys.modules["requests"] = previous
    return namespace


def _requests_module(namespace: dict):
    return namespace["requests"]


def _new_session(namespace: dict, **overrides):
    settings = {
        "base_url": BASE_URL,
        "auth_refresh_path": AUTH_REFRESH_PATH,
        "auth_token": SENSITIVE_TOKEN,
        "timeout_s": 7.5,
        "max_retry_after_s": 2.0,
    }
    settings.update(overrides)
    return namespace["RefreshingSession"](**settings)


def _prepared_request(namespace, method: str = "GET", url: str = f"{BASE_URL}deals"):
    request = _requests_module(namespace).PreparedRequest()
    request.prepare(method=method, url=url, headers={})
    return request


def _install_transport(namespace, monkeypatch, plans, body_reads=None):
    """Install a response queue at the transport boundary and record calls."""
    calls = []
    requests_module = _requests_module(namespace)

    def fake_send(session, request, **kwargs):
        index = len(calls)
        assert index < len(plans), "the recipe sent more requests than allowed"
        plan = plans[index]
        call = {
            "method": request.method,
            "url": request.url,
            "headers": dict(request.headers),
            "kwargs": dict(kwargs),
            "closed": False,
        }
        if body_reads is not None and hasattr(request.body, "read"):
            body_reads.append(request.body.read())
        calls.append(call)
        if isinstance(plan, BaseException):
            raise plan

        status, payload, headers = plan
        class Response:
            def __init__(self) -> None:
                self.status_code = status
                self.url = request.url
                self.request = request
                self.headers = dict(headers or {})
                self._payload = payload

            def json(self):
                if isinstance(self._payload, bytes):
                    return json.loads(self._payload.decode("utf-8"))
                return self._payload

            def close(self) -> None:
                pass

        response = Response()
        original_close = response.close

        def close() -> None:
            call["closed"] = True
            original_close()

        response.close = close
        call["response"] = response
        return response

    monkeypatch.setattr(requests_module.Session, "send", fake_send)
    return calls


def test_refresh_recipe_is_the_shipped_script_and_markdown_has_no_duplicate(
    recipe_namespace,
):
    source = _script_source()
    assert "class RefreshingSession(requests.Session)" in source
    assert "def send(self, request, **kwargs):" in source
    assert "super().send(" in source
    assert "auth_refresh_path" in source
    assert "auth_token" in source
    assert "refresh_endpoint" not in source
    assert "secrets[\"refresh_token\"]" not in source
    assert "import logging" not in source
    assert "print(" not in source
    assert callable(recipe_namespace["make_rest_api_config"])
    doc = _doc()
    assert "../scripts/api_source_refresh_session.py" in doc
    assert "class RefreshingSession(requests.Session)" not in doc
    assert "def _headers_from(" not in doc
    assert "def make_rest_api_config(" not in doc


def test_extracted_recipe_builds_config_from_the_three_flat_profile_keys(
    recipe_namespace,
):
    config = recipe_namespace["make_rest_api_config"](
        {
            "base_url": BASE_URL,
            "auth_refresh_path": AUTH_REFRESH_PATH,
            "auth_token": SENSITIVE_TOKEN,
        },
        [{"name": "deals"}],
    )
    assert config["client"]["base_url"] == BASE_URL
    assert config["client"]["session"]._refresh_url == REFRESH_URL
    assert config["resources"] == [{"name": "deals"}]


def test_config_reconstructs_connector_headers_once_and_shares_them(
    recipe_namespace,
):
    secrets = {
        "base_url": BASE_URL,
        "auth_refresh_path": AUTH_REFRESH_PATH,
        "auth_token": SENSITIVE_TOKEN,
        "header_user_agent": "nexty-test-client/1.0",
        "header_x_trace_id": "trace-123",
    }
    original_headers_from = recipe_namespace["_headers_from"]
    calls = []

    def recording_headers_from(values):
        calls.append(values)
        return original_headers_from(values)

    recipe_namespace["_headers_from"] = recording_headers_from
    try:
        config = recipe_namespace["make_rest_api_config"](secrets, [])
    finally:
        recipe_namespace["_headers_from"] = original_headers_from

    expected = {
        "User-Agent": "nexty-test-client/1.0",
        "X-Trace-Id": "trace-123",
    }
    assert calls == [secrets]
    assert config["client"]["headers"] == expected
    assert config["client"]["session"]._custom_headers == expected


def test_status_only_refresh_retains_the_current_bearer(
    recipe_namespace, monkeypatch
):
    calls = _install_transport(
        recipe_namespace,
        monkeypatch,
        [
            (401, {"error": "expired"}, {}),
            (200, {"status": "refreshed"}, {}),
            (200, {"data": "ok"}, {}),
        ],
    )
    session = _new_session(recipe_namespace)

    response = session.send(_prepared_request(recipe_namespace))

    assert response.status_code == 200
    assert [call["url"] for call in calls] == [
        f"{BASE_URL}deals",
        REFRESH_URL,
        f"{BASE_URL}deals",
    ]
    assert all(
        call["headers"].get("Authorization") == f"Bearer {SENSITIVE_TOKEN}"
        for call in calls
    )
    assert calls[0]["closed"] is True
    assert calls[1]["closed"] is True
    assert calls[2]["closed"] is False
    assert all(call["kwargs"]["timeout"] == 7.5 for call in calls)
    assert all(call["kwargs"]["allow_redirects"] is False for call in calls)


def test_custom_headers_reach_an_ordinary_request(recipe_namespace, monkeypatch):
    calls = _install_transport(
        recipe_namespace,
        monkeypatch,
        [(200, {"data": "ok"}, {})],
    )
    request = _prepared_request(recipe_namespace)
    request.headers["User-Agent"] = "dlt/1.28.2"
    session = _new_session(
        recipe_namespace,
        headers={
            "User-Agent": "nexty-test-client/1.0",
            "X-Trace-Id": "trace-123",
        },
    )

    assert session.send(request).status_code == 200

    assert calls[0]["url"] == f"{BASE_URL}deals"
    assert calls[0]["headers"]["User-Agent"] == "nexty-test-client/1.0"
    assert calls[0]["headers"]["X-Trace-Id"] == "trace-123"
    assert calls[0]["headers"]["Authorization"] == f"Bearer {SENSITIVE_TOKEN}"


def test_custom_headers_reach_root_relative_refresh_request(
    recipe_namespace, monkeypatch
):
    calls = _install_transport(
        recipe_namespace,
        monkeypatch,
        [
            (401, {"error": "expired"}, {}),
            (200, {"access_token": "rotated-test-token"}, {}),
            (200, {"data": "ok"}, {}),
        ],
    )
    session = _new_session(
        recipe_namespace,
        auth_refresh_path="/auth/refresh",
        headers={"User-Agent": "nexty-test-client/1.0", "X-Trace-Id": "trace-123"},
    )

    assert session.send(_prepared_request(recipe_namespace)).status_code == 200

    assert calls[1]["method"] == "POST"
    assert calls[1]["url"] == REFRESH_URL
    assert calls[1]["headers"]["User-Agent"] == "nexty-test-client/1.0"
    assert calls[1]["headers"]["X-Trace-Id"] == "trace-123"
    assert calls[1]["headers"]["Authorization"] == f"Bearer {SENSITIVE_TOKEN}"
    assert calls[2]["headers"]["Authorization"] == "Bearer rotated-test-token"


def test_valid_returned_token_replaces_the_bearer(recipe_namespace, monkeypatch):
    calls = _install_transport(
        recipe_namespace,
        monkeypatch,
        [
            (401, {"error": "expired"}, {}),
            (200, {"access_token": "rotated-test-token"}, {}),
            (200, {"data": "ok"}, {}),
        ],
    )
    session = _new_session(recipe_namespace)

    session.send(_prepared_request(recipe_namespace))

    assert calls[0]["headers"]["Authorization"] == f"Bearer {SENSITIVE_TOKEN}"
    assert calls[1]["headers"]["Authorization"] == f"Bearer {SENSITIVE_TOKEN}"
    assert calls[2]["headers"]["Authorization"] == "Bearer rotated-test-token"


@pytest.mark.parametrize(
    "payload",
    [
        {"access_token": ""},
        {"token": 42},
        {"token": "valid", "access_token": "other"},
    ],
)
def test_present_malformed_or_conflicting_token_fields_fail_without_values(
    recipe_namespace, monkeypatch, payload
):
    calls = _install_transport(
        recipe_namespace,
        monkeypatch,
        [
            (401, {"error": "expired"}, {}),
            (200, payload, {}),
        ],
    )
    session = _new_session(recipe_namespace)

    with pytest.raises(RuntimeError) as raised:
        session.send(_prepared_request(recipe_namespace))

    assert SENSITIVE_TOKEN not in str(raised.value)
    assert len(calls) == 2
    assert calls[0]["closed"] is True
    assert calls[1]["closed"] is True


def test_non_2xx_refresh_fails_without_copying_the_response_body(
    recipe_namespace, monkeypatch
):
    calls = _install_transport(
        recipe_namespace,
        monkeypatch,
        [
            (401, {"error": "expired"}, {}),
            (503, {"error": SENSITIVE_TOKEN}, {}),
        ],
    )
    session = _new_session(recipe_namespace)

    with pytest.raises(RuntimeError, match="non-2xx") as raised:
        session.send(_prepared_request(recipe_namespace))

    assert SENSITIVE_TOKEN not in str(raised.value)
    assert len(calls) == 2
    assert calls[0]["closed"] is True
    assert calls[1]["closed"] is True


def test_second_401_fails_immediately_after_one_refresh(
    recipe_namespace, monkeypatch
):
    calls = _install_transport(
        recipe_namespace,
        monkeypatch,
        [
            (401, {"error": "expired"}, {}),
            (200, {"token": "rotated-test-token"}, {}),
            (401, {"error": "still expired"}, {}),
        ],
    )
    session = _new_session(recipe_namespace)

    with pytest.raises(RuntimeError, match="one refresh"):
        session.send(_prepared_request(recipe_namespace))

    assert len(calls) == 3
    assert all(call["closed"] is True for call in calls)


@pytest.mark.parametrize(
    ("retry_after", "expected_delay"),
    [
        ("not-a-number", 0.0),
        ("-5", 0.0),
        ("NaN", 0.0),
        ("999999", 2.0),
        ("Infinity", 2.0),
    ],
)
def test_retry_after_is_defensive_and_capped(
    recipe_namespace, monkeypatch, retry_after, expected_delay
):
    calls = _install_transport(
        recipe_namespace,
        monkeypatch,
        [
            (429, {"error": "rate limited"}, {"Retry-After": retry_after}),
            (200, {"data": "ok"}, {}),
        ],
    )
    delays = []
    monkeypatch.setattr(recipe_namespace["time"], "sleep", delays.append)
    session = _new_session(recipe_namespace)

    assert session.send(_prepared_request(recipe_namespace)).status_code == 200

    assert delays == [expected_delay]
    assert len(calls) == 2
    assert calls[0]["closed"] is True
    assert calls[1]["closed"] is False


def test_only_one_429_retry_is_allowed(recipe_namespace, monkeypatch):
    calls = _install_transport(
        recipe_namespace,
        monkeypatch,
        [
            (429, {"error": "rate limited"}, {"Retry-After": "999"}),
            (429, {"error": "still limited"}, {"Retry-After": "999"}),
        ],
    )
    delays = []
    monkeypatch.setattr(recipe_namespace["time"], "sleep", delays.append)
    session = _new_session(recipe_namespace)

    response = session.send(_prepared_request(recipe_namespace))

    assert response.status_code == 429
    assert delays == [2.0]
    assert len(calls) == 2
    assert calls[0]["closed"] is True
    assert calls[1]["closed"] is False


def test_replayable_post_body_survives_refresh_replay(recipe_namespace, monkeypatch):
    body = io.BytesIO(b'{"query":"query { deals { id } }"}')
    request = _prepared_request(recipe_namespace, "POST")
    request.body = body
    request.headers["Content-Type"] = "application/json"
    observed_bodies = []
    calls = _install_transport(
        recipe_namespace,
        monkeypatch,
        [
            (401, {"error": "expired"}, {}),
            (200, {"access_token": "rotated-test-token"}, {}),
            (200, {"data": "ok"}, {}),
        ],
        body_reads=observed_bodies,
    )
    session = _new_session(recipe_namespace)

    assert session.send(request).status_code == 200

    assert observed_bodies == [body.getvalue(), body.getvalue()]
    assert calls[0]["method"] == "POST"
    assert calls[2]["method"] == "POST"


def test_non_rewindable_stream_is_rejected_before_transport(
    recipe_namespace, monkeypatch
):
    class NonRewindableStream:
        def read(self):
            return b"one-shot"

    calls = _install_transport(
        recipe_namespace, monkeypatch, [(200, {"data": "ok"}, {})]
    )
    request = _prepared_request(recipe_namespace, "POST")
    request.body = NonRewindableStream()
    session = _new_session(recipe_namespace)

    with pytest.raises(TypeError, match="replayable"):
        session.send(request)

    assert calls == []


def test_refresh_path_is_relative_and_same_origin_without_echoing_credentials(
    recipe_namespace,
):
    session_class = recipe_namespace["RefreshingSession"]
    for refresh_path in (
        "https://evil.example.test/refresh",
        "//evil.example.test/refresh",
        "auth/refresh?token=" + SENSITIVE_TOKEN,
    ):
        with pytest.raises(ValueError) as raised:
            session_class(
                base_url=BASE_URL,
                auth_refresh_path=refresh_path,
                auth_token=SENSITIVE_TOKEN,
            )
        assert SENSITIVE_TOKEN not in str(raised.value)


@pytest.mark.parametrize(
    "header_name",
    ["Authorization", "authorization", "aUtHoRiZaTiOn"],
)
def test_caller_authorization_override_is_rejected_case_insensitively(
    recipe_namespace, monkeypatch, header_name
):
    calls = _install_transport(
        recipe_namespace, monkeypatch, [(200, {"data": "ok"}, {})]
    )
    request = _prepared_request(recipe_namespace)
    request.headers[header_name] = "caller-supplied-token"
    session = _new_session(recipe_namespace, auth_refresh_path="/auth/refresh")

    with pytest.raises(ValueError, match="Authorization") as raised:
        session.send(request)

    assert "caller-supplied-token" not in str(raised.value)
    assert calls == []


def test_cross_origin_redirect_is_not_followed(recipe_namespace, monkeypatch):
    calls = _install_transport(
        recipe_namespace,
        monkeypatch,
        [
            (401, {"error": "expired"}, {}),
            (
                302,
                {"error": "redirect"},
                {"Location": "https://evil.example.test/steal"},
            ),
        ],
    )
    session = _new_session(recipe_namespace)

    with pytest.raises(RuntimeError, match="non-2xx"):
        session.send(_prepared_request(recipe_namespace))

    assert len(calls) == 2
    assert calls[1]["kwargs"]["allow_redirects"] is False
    assert all("evil.example.test" not in call["url"] for call in calls)


def test_refresh_transport_error_is_wrapped_without_exposing_credential(
    recipe_namespace, monkeypatch
):
    calls = _install_transport(
        recipe_namespace,
        monkeypatch,
        [
            (401, {"error": "expired"}, {}),
            RuntimeError("transport token=" + SENSITIVE_TOKEN),
        ],
    )
    session = _new_session(recipe_namespace)

    with pytest.raises(RuntimeError, match="refresh request failed") as raised:
        session.send(_prepared_request(recipe_namespace))

    assert SENSITIVE_TOKEN not in str(raised.value)
    assert len(calls) == 2
    assert calls[0]["closed"] is True

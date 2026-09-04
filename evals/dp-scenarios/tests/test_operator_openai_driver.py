"""Contract tests for the OpenAI chat-completions driver provider.

Every test in this file runs with the network physically unavailable: the
autouse fixture replaces ``aiohttp.ClientSession`` and ``socket.create_connection``
with functions that raise. A test that starts making a real call fails here
rather than quietly billing an account.
"""

from __future__ import annotations

import json
import socket
from dataclasses import replace
from typing import Any

import aiohttp
import pytest

from dp_scenarios.operator.driver import DriverBeat, DriverView
from dp_scenarios.operator.openai_driver import (
    SYSTEM_PROMPT,
    DriverConfigError,
    DriverProviderError,
    OpenAIDriverProvider,
    _aiohttp_post,
    build_messages,
    driver_prompt_hash,
)


@pytest.fixture(autouse=True)
def _no_network(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make any real outbound call an immediate, loud failure."""

    def refuse(*args: object, **kwargs: object) -> None:
        raise AssertionError("test attempted a real network call")

    monkeypatch.setattr(aiohttp, "ClientSession", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)


def make_view(**overrides: Any) -> DriverView:
    """Build a driver view with every field populated and distinguishable."""

    base = dict(
        turn=4,
        phase=2,
        persona_id="ops-lead",
        persona_label="Head of Operations",
        persona_vocabulary=("shipments", "carrier"),
        persona_behaviors=("impatient",),
        agent_message="Which system holds the shipment records?",
        selected_reply="They live in the carrier portal.",
        prior_operator_messages=("We need a weekly shipment view.",),
        remaining_turns=6,
        prior_agent_messages=("Understood, starting now.",),
        known_facts=(("infra", "Everything is in the carrier portal, exported nightly."),),
        facts_already_stated=("volume",),
        beat=DriverBeat("card-1", ("carrier portal outage", "since Tuesday")),
        forbidden_terms=("late delivery rate",),
        rejection_notice=None,
    )
    base.update(overrides)
    return DriverView(**base)  # type: ignore[arg-type]


def _payload(content: str) -> dict[str, object]:
    return {"choices": [{"message": {"role": "assistant", "content": content}}]}


# --------------------------------------------------------------------------
# Key containment
# --------------------------------------------------------------------------


def test_from_environment_refuses_when_the_key_is_absent(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    with pytest.raises(DriverConfigError, match="OPENAI_API_KEY is not set in the environment"):
        OpenAIDriverProvider.from_environment(model="m", temperature=0.7)


@pytest.mark.parametrize("value", ["", "   ", "\n"])
def test_from_environment_refuses_a_blank_key(monkeypatch: pytest.MonkeyPatch, value: str) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", value)

    with pytest.raises(DriverConfigError, match="OPENAI_API_KEY is not set in the environment"):
        OpenAIDriverProvider.from_environment(model="m", temperature=0.7)


@pytest.mark.parametrize("missing", [None, "", "   ", "\n"])
def test_the_key_guard_lives_in_from_environment_and_not_only_in_the_constructor(
    monkeypatch: pytest.MonkeyPatch, missing: str | None
) -> None:
    """Pin the refusal to the helper rather than to ``__post_init__``.

    ``__post_init__`` rejects a blank key with the same message, so the two
    tests above pass unchanged even when ``from_environment``'s own guard is
    deleted -- the constructor silently covers for it. That makes the guard a
    gate that never fires, and it would stop firing for real the day the
    constructor is relaxed to allow an empty key (a local or proxied
    endpoint), at which point a missing environment variable would build an
    unauthenticated provider instead of refusing. Ask a subclass that
    validates nothing, so only the helper's guard can raise, and count
    constructions so the guard is shown to refuse *before* building rather
    than to build and then reject.
    """

    constructed: list[OpenAIDriverProvider] = []

    class Permissive(OpenAIDriverProvider):
        __slots__ = ()

        def __post_init__(self) -> None:
            constructed.append(self)
            object.__setattr__(self, "base_url", self.base_url.rstrip("/"))

    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    assert Permissive.from_environment(model="m", temperature=0.7).api_key == "sk-test"
    assert len(constructed) == 1

    if missing is None:
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    else:
        monkeypatch.setenv("OPENAI_API_KEY", missing)
    with pytest.raises(DriverConfigError, match="OPENAI_API_KEY is not set in the environment"):
        Permissive.from_environment(model="m", temperature=0.7)
    assert len(constructed) == 1


def test_from_environment_reads_only_the_environment_variable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")

    provider = OpenAIDriverProvider.from_environment(model="m", temperature=0.4, timeout_seconds=12.0)

    assert provider.api_key == "sk-test"
    assert provider.model == "m"
    assert provider.temperature == 0.4
    assert provider.timeout_seconds == 12.0


def test_repr_and_str_never_carry_the_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    provider = OpenAIDriverProvider.from_environment(model="m", temperature=0.7)

    for text in (repr(provider), str(provider), f"{provider}", format(provider)):
        assert "sk-test" not in text
        assert "Bearer" not in text
    # The representation is still useful, not merely empty.
    assert "model='m'" in repr(provider)
    assert "api_key=<redacted>" in repr(provider)


def test_a_failing_post_cannot_carry_the_key_into_the_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")

    def leaking_post(url: str, headers: Any, body: Any, timeout: float) -> Any:
        raise RuntimeError(f"upstream rejected {headers['Authorization']} for {url}")

    provider = OpenAIDriverProvider.from_environment(model="m", temperature=0.7, post=leaking_post)

    with pytest.raises(DriverProviderError) as excinfo:
        provider(make_view())
    message = str(excinfo.value)
    assert "sk-test" not in message
    assert "Bearer" not in message
    assert "<redacted>" in message
    # The chained cause is dropped rather than re-raised: an implicit
    # __context__ would put the unscrubbed original back into a traceback.
    assert excinfo.value.__cause__ is None
    assert excinfo.value.__suppress_context__ is True


def test_a_provider_error_raised_by_the_transport_is_scrubbed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")

    def leaking_post(url: str, headers: Any, body: Any, timeout: float) -> Any:
        raise DriverProviderError("provider returned HTTP 401: {'sent': 'Bearer sk-test'}")

    provider = OpenAIDriverProvider.from_environment(model="m", temperature=0.7, post=leaking_post)

    with pytest.raises(DriverProviderError) as excinfo:
        provider(make_view())
    assert "sk-test" not in str(excinfo.value)
    assert "Bearer" not in str(excinfo.value)
    assert "HTTP 401" in str(excinfo.value)


# --------------------------------------------------------------------------
# The request and the response
# --------------------------------------------------------------------------


def test_the_request_carries_the_documented_url_headers_and_body(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    seen: dict[str, Any] = {}

    def fake_post(url: str, headers: Any, body: Any, timeout: float) -> Any:
        seen.update(url=url, headers=dict(headers), body=dict(body), timeout=timeout)
        return _payload("  They live in the carrier portal.  ")

    provider = OpenAIDriverProvider.from_environment(
        model="gpt-x",
        temperature=0.3,
        timeout_seconds=9.0,
        post=fake_post,
    )

    assert provider(make_view()) == "They live in the carrier portal."
    assert seen["url"] == "https://api.openai.com/v1/chat/completions"
    assert seen["headers"]["Authorization"] == "Bearer sk-test"
    assert seen["headers"]["Content-Type"] == "application/json"
    assert seen["timeout"] == 9.0
    assert seen["body"]["model"] == "gpt-x"
    assert seen["body"]["temperature"] == 0.3
    assert seen["body"]["max_completion_tokens"] == 400
    # The old name must be gone, not merely accompanied: GPT-5-class models
    # reject the request outright when it is present.
    assert "max_tokens" not in seen["body"]
    assert seen["body"]["messages"] == build_messages(make_view())


def test_a_custom_base_url_is_honoured_without_a_double_slash(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    seen: dict[str, Any] = {}

    def fake_post(url: str, headers: Any, body: Any, timeout: float) -> Any:
        seen["url"] = url
        return _payload("fine")

    provider = OpenAIDriverProvider.from_environment(
        model="m",
        temperature=0.0,
        base_url="https://proxy.internal/v1/",
        post=fake_post,
    )
    provider(make_view())

    assert seen["url"] == "https://proxy.internal/v1/chat/completions"


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"choices": []},
        {"choices": [{}]},
        {"choices": [{"message": {}}]},
        {"choices": [{"message": {"content": None}}]},
        {"choices": [{"message": {"content": ""}}]},
        {"choices": [{"message": {"content": "   \n  "}}]},
        {"choices": [{"message": {"content": 17}}]},
        {"choices": "text"},
        {"choices": [{"message": "text"}]},
        [],
        "not-json-object",
    ],
    ids=lambda value: repr(value)[:40],
)
def test_a_malformed_payload_is_refused(monkeypatch: pytest.MonkeyPatch, payload: object) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    provider = OpenAIDriverProvider.from_environment(
        model="m",
        temperature=0.0,
        post=lambda url, headers, body, timeout: payload,  # type: ignore[arg-type,return-value]
    )

    with pytest.raises(DriverProviderError, match="provider returned no text"):
        provider(make_view())


def test_configuration_is_validated_at_construction(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")

    with pytest.raises(DriverConfigError, match="temperature"):
        OpenAIDriverProvider.from_environment(model="m", temperature=2.5)
    with pytest.raises(DriverConfigError, match="model"):
        OpenAIDriverProvider.from_environment(model="  ", temperature=0.5)
    with pytest.raises(DriverConfigError, match="timeout"):
        OpenAIDriverProvider.from_environment(model="m", temperature=0.5, timeout_seconds=0)
    with pytest.raises(DriverConfigError, match="max_tokens"):
        OpenAIDriverProvider.from_environment(model="m", temperature=0.5, max_tokens=0)
    with pytest.raises(DriverConfigError, match="OPENAI_API_KEY"):
        OpenAIDriverProvider(model="m", temperature=0.5, api_key="  ")


def test_the_default_transport_is_the_aiohttp_call(monkeypatch: pytest.MonkeyPatch) -> None:
    """With ``post`` unset the provider must go through aiohttp, not a stub."""

    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    provider = OpenAIDriverProvider.from_environment(model="m", temperature=0.0)

    with pytest.raises(DriverProviderError) as excinfo:
        provider(make_view())
    # The autouse fixture's AssertionError is what the aiohttp path hits.
    assert "AssertionError" in str(excinfo.value)


# --------------------------------------------------------------------------
# The aiohttp transport itself
# --------------------------------------------------------------------------


class _FakeResponse:
    def __init__(self, status: int, body: str) -> None:
        self.status = status
        self._body = body

    async def text(self) -> str:
        return self._body

    async def __aenter__(self) -> "_FakeResponse":
        return self

    async def __aexit__(self, *exc: object) -> bool:
        return False


class _FakeSession:
    last: dict[str, Any] = {}

    def __init__(self, *, timeout: object = None) -> None:
        _FakeSession.last["timeout"] = timeout

    async def __aenter__(self) -> "_FakeSession":
        return self

    async def __aexit__(self, *exc: object) -> bool:
        return False

    def post(self, url: str, headers: Any = None, json: Any = None) -> _FakeResponse:
        _FakeSession.last.update(url=url, headers=headers, json=json)
        return _FakeResponse(_FakeSession.last["status"], _FakeSession.last["body"])


def _install_fake_session(monkeypatch: pytest.MonkeyPatch, *, status: int, body: str) -> None:
    _FakeSession.last = {"status": status, "body": body}
    monkeypatch.setattr(aiohttp, "ClientSession", _FakeSession)


def test_aiohttp_post_decodes_a_success_and_applies_the_total_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_fake_session(monkeypatch, status=200, body=json.dumps(_payload("hello")))

    result = _aiohttp_post("https://example/chat/completions", {"A": "b"}, {"model": "m"}, 7.5)

    assert result == _payload("hello")
    assert _FakeSession.last["url"] == "https://example/chat/completions"
    assert _FakeSession.last["headers"] == {"A": "b"}
    assert _FakeSession.last["json"] == {"model": "m"}
    assert _FakeSession.last["timeout"].total == 7.5


def test_aiohttp_post_reports_the_status_and_a_bounded_body_on_a_non_2xx(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_fake_session(monkeypatch, status=429, body="x" * 900)

    with pytest.raises(DriverProviderError) as excinfo:
        _aiohttp_post("https://example/chat/completions", {}, {}, 1.0)
    message = str(excinfo.value)
    assert "HTTP 429" in message
    assert message.count("x") == 300


def test_aiohttp_post_refuses_undecodable_json(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_fake_session(monkeypatch, status=200, body="<html>gateway</html>")

    with pytest.raises(DriverProviderError, match="undecodable JSON"):
        _aiohttp_post("https://example/chat/completions", {}, {}, 1.0)


# --------------------------------------------------------------------------
# The prompt
# --------------------------------------------------------------------------


def test_build_messages_carries_every_field_the_prompt_relies_on() -> None:
    view = make_view(rejection_notice="leading: late delivery rate")
    messages = build_messages(view)

    assert [message["role"] for message in messages] == ["system", "user"]
    system, user = messages[0]["content"], messages[1]["content"]
    assert SYSTEM_PROMPT in system
    assert "Head of Operations" in system
    assert "shipments" in system
    assert "impatient" in system

    for _key, text in view.known_facts:
        assert text in user
    assert view.beat is not None
    for term in view.beat.required_terms:
        assert term in user
    for term in view.forbidden_terms:
        assert term in user
    assert "leading: late delivery rate" in user
    assert view.agent_message in user
    assert view.selected_reply in user
    for message in view.prior_agent_messages:
        assert message in user
    for fact_key in view.facts_already_stated:
        assert fact_key in user


def test_build_messages_serialises_the_whole_view_deterministically() -> None:
    view = make_view()
    first = build_messages(view)
    second = build_messages(view)

    assert first == second
    assert json.loads(first[1]["content"]) == json.loads(
        json.dumps(view.to_mapping(), ensure_ascii=False, sort_keys=True, indent=2)
    )
    # Sorted keys, so the diff between two turns is the content, not the order.
    assert list(json.loads(first[1]["content"])) == sorted(json.loads(first[1]["content"]))


def test_build_messages_shows_no_beat_when_the_turn_has_none() -> None:
    payload = json.loads(build_messages(make_view(beat=None))[1]["content"])

    assert payload["beat"] is None


def test_the_prompt_states_the_rules_the_checks_enforce() -> None:
    lowered = SYSTEM_PROMPT.lower()

    for phrase in (
        "known_facts",
        "forbidden_terms",
        "facts_already_stated",
        "rejection_notice",
        "beat",
        "selected_reply",
        "grain",
        "joins",
        "aggregation",
        "columns",
    ):
        assert phrase in lowered, phrase


def test_the_prompt_hash_is_the_digest_of_the_prompt_text() -> None:
    import hashlib

    assert driver_prompt_hash() == hashlib.sha256(SYSTEM_PROMPT.encode("utf-8")).hexdigest()
    assert len(driver_prompt_hash()) == 64
    assert driver_prompt_hash() == driver_prompt_hash()


def test_the_prompt_hash_changes_when_the_prompt_changes(monkeypatch: pytest.MonkeyPatch) -> None:
    before = driver_prompt_hash()
    monkeypatch.setattr(
        "dp_scenarios.operator.openai_driver.SYSTEM_PROMPT",
        SYSTEM_PROMPT + " one more rule.",
    )

    assert driver_prompt_hash() != before


def test_the_view_the_provider_sends_is_only_the_views_own_mapping() -> None:
    """No harness state may reach the wire beyond the redacted view."""

    view = make_view()
    payload = json.loads(build_messages(view)[1]["content"])

    assert set(payload) == set(view.to_mapping())


def test_a_replaced_view_is_still_serialisable() -> None:
    """The driver's re-ask ladder rebuilds the view with ``replace``."""

    view = replace(make_view(), rejection_notice="beat: missing required beat terms: x")
    payload = json.loads(build_messages(view)[1]["content"])

    assert payload["rejection_notice"] == "beat: missing required beat terms: x"


def test_the_default_temperature_is_omitted_rather_than_sent(monkeypatch: pytest.MonkeyPatch) -> None:
    """GPT-5-class models reject `temperature` unless it is left at the default.

    Omitting it there means the same request, so a driver run against those
    models works; a non-default value is still sent, so it fails loudly instead
    of being quietly dropped.
    """

    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    seen: dict[str, Any] = {}

    def fake_post(url: str, headers: Any, body: Any, timeout: float) -> Any:
        seen["body"] = body
        return {"choices": [{"message": {"content": "ok"}}]}

    def provider_at(temperature: float) -> Any:
        return OpenAIDriverProvider(
            model="gpt-x",
            temperature=temperature,
            api_key="sk-test",
            timeout_seconds=9.0,
            post=fake_post,
        )

    provider_at(1.0)(make_view())
    assert "temperature" not in seen["body"]

    provider_at(0.3)(make_view())
    assert seen["body"]["temperature"] == 0.3

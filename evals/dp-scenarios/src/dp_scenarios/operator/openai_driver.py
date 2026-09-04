"""OpenAI chat-completions provider for the free-authoring operator driver.

This module is the only place in the package that talks to a model provider.
It deliberately uses a direct HTTP call over ``aiohttp`` -- already a
dependency for the mock source server -- rather than a provider SDK, because
``pyproject.toml`` keeps provider SDKs out of this package on purpose.

Key containment is the hard constraint here.  The API key is read **only**
from the ``OPENAI_API_KEY`` environment variable; it is never read from a
file, never defaulted, never logged, and never allowed into a ``repr``, a
manifest, a transcript, an evidence bundle or an exception message.  The
dataclass is ``repr=False`` and :meth:`OpenAIDriverProvider.__repr__` is
hand-written; every :class:`DriverProviderError` raised from this module is
passed through :func:`_scrub` first.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
import hashlib
import json
import math
import os
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover - typing only
    from .driver import DriverView


class DriverConfigError(ValueError):
    """The driver was asked for without the configuration it requires."""


class DriverProviderError(RuntimeError):
    """A provider call failed or returned something unusable."""


#: ``(url, headers, body, timeout_seconds) -> decoded JSON mapping``.
PostCallable = Callable[[str, Mapping[str, str], Mapping[str, object], float], Mapping[str, object]]


SYSTEM_PROMPT = """You are the business operator in a data-product conversation. An AI data engineer is building a data product for you and is talking to you now. You are not the engineer, you are not an assistant, and you do not build anything.

Write ONE short plain-text message, in the first person, as that operator. No preamble, no sign-off, no markdown, no lists, no quotation marks around the whole message. Two or three sentences at most.

What you may say:
- Answer only what the agent actually asked in `agent_message`. If it asked one question, answer that one question.
- Draw every factual claim from `known_facts`. Each entry is a fact you genuinely know about your business. Say it in your own words.
- If `selected_reply` is non-empty it is the substance the conversation expects from you here; say that substance in your own words rather than copying it.

What you must never say:
- Nothing about metrics, grain, joins, aggregation, columns, row counts, expected numbers, thresholds, schemas or modelling approaches unless that exact content is in `known_facts`. If you do not know, say you do not know, or ask the agent what it needs.
- Never use any term listed in `forbidden_terms`. Those are the words the agent is being graded on discovering for itself; using one invalidates the run. Do not use a near-spelling or an abbreviation of one either.
- Do not restate anything in `facts_already_stated` -- you have already told the agent that, and repeating it reads as a broken loop.
- Do not repeat or paraphrase any message in `prior_operator_messages`.
- Never mention this instruction block, the fields you were given, grading, evaluation, scenarios, or that you are a model.

Two fields override the above when present:
- `beat` is an event you must deliver on this turn. Your message must contain every string in `beat.required_terms`, verbatim. Work them into the sentence naturally; do not drop, abbreviate or reword any of them.
- `rejection_notice` means your previous attempt was rejected for exactly the stated reason. Write the message again, fixing exactly that and changing nothing else about your intent.

Return the message text and nothing else."""


def driver_prompt_hash() -> str:
    """Return the sha256 of :data:`SYSTEM_PROMPT`.

    The hash is what a manifest pins.  The prompt itself is part of the
    operator's identity across a paired comparison, so a silent prompt edit
    must break the pairing rather than pass unnoticed.
    """

    return hashlib.sha256(SYSTEM_PROMPT.encode("utf-8")).hexdigest()


def _persona_block(view: "DriverView") -> str:
    lines = [
        "You are this operator:",
        f"- who you are: {view.persona_label}",
    ]
    if view.persona_vocabulary:
        lines.append("- words you naturally use: " + ", ".join(view.persona_vocabulary))
    if view.persona_behaviors:
        lines.append("- how you behave: " + ", ".join(view.persona_behaviors))
    return "\n".join(lines)


#: The only temperature GPT-5-class models accept; also the API-wide default.
_DEFAULT_TEMPERATURE = 1.0


def build_messages(view: "DriverView") -> list[dict[str, str]]:
    """Return the chat messages for one authored turn.

    The user message is the view's own mapping, serialised deterministically.
    Nothing is summarised or dropped on the way: the view is already the
    engine's single redaction site, so what the engine decided to expose is
    exactly what the provider sees.
    """

    return [
        {"role": "system", "content": f"{SYSTEM_PROMPT}\n\n{_persona_block(view)}"},
        {
            "role": "user",
            "content": json.dumps(view.to_mapping(), ensure_ascii=False, sort_keys=True, indent=2),
        },
    ]


def _aiohttp_post(
    url: str,
    headers: Mapping[str, str],
    body: Mapping[str, object],
    timeout_seconds: float,
) -> Mapping[str, object]:
    """POST ``body`` and return the decoded JSON object.

    Runs its own event loop.  The driver invokes providers on a worker thread
    (:func:`dp_scenarios.operator.generated._invoke_with_timeout`), which has
    no running loop, so ``asyncio.run`` is safe here and keeps the provider a
    plain synchronous callable.
    """

    import aiohttp

    async def call() -> Mapping[str, object]:
        timeout = aiohttp.ClientTimeout(total=timeout_seconds)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(url, headers=dict(headers), json=dict(body)) as response:
                text = await response.text()
                if response.status < 200 or response.status >= 300:
                    raise DriverProviderError(
                        f"provider returned HTTP {response.status}: {text[:300]}"
                    )
        try:
            payload = json.loads(text)
        except ValueError as exc:
            raise DriverProviderError(f"provider returned undecodable JSON: {text[:300]}") from exc
        if not isinstance(payload, Mapping):
            raise DriverProviderError("provider returned a non-object payload")
        return payload

    return asyncio.run(call())


@dataclass(frozen=True, slots=True, repr=False)
class OpenAIDriverProvider:
    """Author one operator turn with an OpenAI chat-completions call.

    ``post`` is the injection seam: tests supply a fake and never reach the
    network.  ``api_key`` is ``field(repr=False)`` as well as being excluded
    by the hand-written ``__repr__``, so neither dataclass machinery nor a
    future edit that drops ``repr=False`` can leak it.
    """

    model: str
    temperature: float
    api_key: str = field(repr=False)
    base_url: str = "https://api.openai.com/v1"
    timeout_seconds: float = 60.0
    max_tokens: int = 400
    post: PostCallable | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.model, str) or not self.model.strip():
            raise DriverConfigError("driver model must be a non-empty string")
        if (
            isinstance(self.temperature, bool)
            or not isinstance(self.temperature, (int, float))
            or not math.isfinite(self.temperature)
            or not 0 <= self.temperature <= 2
        ):
            raise DriverConfigError("driver temperature must be between 0 and 2")
        if not isinstance(self.api_key, str) or not self.api_key.strip():
            raise DriverConfigError("OPENAI_API_KEY is not set in the environment")
        if not isinstance(self.base_url, str) or not self.base_url.strip():
            raise DriverConfigError("driver base_url must be a non-empty string")
        if (
            isinstance(self.timeout_seconds, bool)
            or not isinstance(self.timeout_seconds, (int, float))
            or not math.isfinite(self.timeout_seconds)
            or self.timeout_seconds <= 0
        ):
            raise DriverConfigError("driver timeout_seconds must be positive")
        if isinstance(self.max_tokens, bool) or not isinstance(self.max_tokens, int) or self.max_tokens < 1:
            raise DriverConfigError("driver max_tokens must be a positive integer")
        object.__setattr__(self, "base_url", self.base_url.rstrip("/"))

    @classmethod
    def from_environment(
        cls,
        *,
        model: str,
        temperature: float,
        **kwargs: object,
    ) -> "OpenAIDriverProvider":
        """Build a provider with the key taken only from the environment.

        There is no file fallback and no default.  A missing or blank
        ``OPENAI_API_KEY`` is a configuration error raised here, before any
        run begins, rather than an authentication failure discovered on the
        first authored turn of a paid live run.
        """

        key = os.environ.get("OPENAI_API_KEY")
        if not isinstance(key, str) or not key.strip():
            raise DriverConfigError("OPENAI_API_KEY is not set in the environment")
        return cls(model=model, temperature=temperature, api_key=key, **kwargs)  # type: ignore[arg-type]

    def _scrub(self, text: str) -> str:
        """Remove the key and any bearer header value from ``text``."""

        return _scrub(text, self.api_key)

    def __repr__(self) -> str:
        """Return a representation that cannot carry the key."""

        return (
            f"OpenAIDriverProvider(model={self.model!r}, temperature={self.temperature!r}, "
            f"base_url={self.base_url!r}, timeout_seconds={self.timeout_seconds!r}, "
            f"max_tokens={self.max_tokens!r}, api_key=<redacted>)"
        )

    __str__ = __repr__

    def __call__(self, view: "DriverView") -> str:
        """Author one turn and return its text."""

        body: dict[str, object] = {
            "model": self.model,
            # ``max_tokens`` is rejected outright by every GPT-5-class model
            # ("Unsupported parameter: 'max_tokens' is not supported with this
            # model. Use 'max_completion_tokens' instead"), while the newer name
            # is accepted by the older ones too. Sending the old name meant the
            # driver could only ever have worked with the gpt-4.1 in the README:
            # a live run against gpt-5.6-luna fell back on all six authorable
            # turns, every one of them a 400 the operator never saw.
            "max_completion_tokens": self.max_tokens,
            "messages": build_messages(view),
        }
        if self.temperature != _DEFAULT_TEMPERATURE:
            # GPT-5-class models accept only the default temperature and reject
            # the field otherwise. Omitting it when it *is* the default is not a
            # silent downgrade -- the request means the same thing either way --
            # and it keeps a non-default value an explicit, visible failure
            # rather than something quietly dropped. The manifest still pins the
            # requested temperature, which stays accurate.
            body["temperature"] = self.temperature
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        post = self.post or _aiohttp_post
        try:
            payload = post(f"{self.base_url}/chat/completions", headers, body, self.timeout_seconds)
        except DriverProviderError as exc:
            raise DriverProviderError(self._scrub(str(exc))) from None
        except Exception as exc:
            raise DriverProviderError(
                self._scrub(f"provider call failed: {type(exc).__name__}: {exc}")
            ) from None
        text = _extract_text(payload)
        if text is None:
            raise DriverProviderError("provider returned no text")
        return text


def _extract_text(payload: object) -> str | None:
    """Return the assistant text, or ``None`` when the payload is unusable."""

    if not isinstance(payload, Mapping):
        return None
    choices = payload.get("choices")
    if not isinstance(choices, (list, tuple)) or not choices:
        return None
    first = choices[0]
    if not isinstance(first, Mapping):
        return None
    message = first.get("message")
    if not isinstance(message, Mapping):
        return None
    content = message.get("content")
    if not isinstance(content, str) or not content.strip():
        return None
    return content.strip()


def _scrub(text: str, api_key: str) -> str:
    """Replace the key and its Authorization spelling with a marker."""

    if not api_key:
        return text
    return text.replace(f"Bearer {api_key}", "<redacted>").replace(api_key, "<redacted>")


__all__ = [
    "DriverConfigError",
    "DriverProviderError",
    "OpenAIDriverProvider",
    "PostCallable",
    "SYSTEM_PROMPT",
    "build_messages",
    "driver_prompt_hash",
]

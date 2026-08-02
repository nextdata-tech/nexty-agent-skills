"""Provider abstraction: where the model call physically happens.

`transport.py` owns the Anthropic wire contract — `output_config.format`,
adaptive thinking, the four `AttemptOutcome`s, budget and backoff. This module
owns the narrower question of *which* endpoint a request is dispatched to, so a
cheap local runner can stand in for the paid API during development without the
harness above it knowing.

Two providers today:

- `anthropic` — the real API via the SDK. Schema-enforced by
  `output_config.format`, so a response either parses against the wire schema or
  is a `SCHEMA_REJECT`. This is the contract of record.
- `claude_cli` — the local `claude -p` binary. **A development aid, not an
  equivalent.** It has no `output_config`, so the schema is a request in prose
  and the harness validates after the fact. See `ClaudeCliProvider` for the full
  list of what differs; the differences are recorded on every result rather than
  smoothed over, because a fixture recorded under one provider and replayed as if
  it came from the other would be a lie about what was tested.

The seam is deliberately thin. A provider receives an already-built request and
returns a raw response object; it does not classify outcomes, count budget,
retry, or write the ledger. Those stay in `transport.py` so both providers are
governed by exactly one failure policy.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from dataclasses import dataclass, field as dc_field
from typing import Any, Mapping, Protocol, Sequence

from .errors import (
    DependencyMissingError,
    ModelNotFoundError,
    SpecError,
    TransportExhaustedError,
)

__all__ = [
    "PROVIDER_KINDS",
    "ProviderResponse",
    "Provider",
    "AnthropicProvider",
    "ClaudeCliProvider",
    "build_provider",
]

#: Closed set, so a typo is a spec error rather than a silent fallback to the
#: paid path.
PROVIDER_KINDS = ("anthropic", "claude_cli")

#: `claude -p` accepts model aliases; the harness records what came back.
_CLI_DEFAULT_MODEL = "sonnet"

#: A fenced code block, optionally tagged. `claude -p` wraps JSON in one even
#: when told not to — it has no structured-output mode to enforce otherwise.
#:
#: Deliberately NOT anchored to the end of the string. An observed real response
#: put an explanatory paragraph *after* the closing fence ("Top line: invoice ref
#: ABC-1023..."), which an end-anchored pattern fails to match — sending the whole
#: blob, prose and all, to the JSON parser. The model's JSON was perfectly valid;
#: only the extraction was wrong. Search for the block, do not require the
#: response to be nothing but the block.
_FENCE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL)


@dataclass
class ProviderResponse:
    """A response shaped like the SDK's `Message`, for `transport._interpret`.

    Deliberately duck-typed rather than importing the SDK type: this module must
    import cleanly with `anthropic` absent, which is the state of the desktop venv
    today. `transport._interpret` reads `stop_reason`, `model`, `content`, and
    `usage` via `getattr`, so matching those four is sufficient.

    `provider_notes` carries any way this response is NOT what the Anthropic API
    would have returned. It is recorded on the attempt so a ledger line says which
    provider produced it and how that provider differs. A response with notes must
    never be checked in as a fixture's `recorded.json` without those notes
    surviving alongside it.
    """

    stop_reason: str | None
    model: str | None
    content: list[Any]
    usage: Any
    provider: str = "anthropic"
    provider_notes: tuple[str, ...] = ()


@dataclass
class _TextBlock:
    text: str
    type: str = "text"


@dataclass
class _Usage:
    input_tokens: int = 0
    output_tokens: int = 0


def _strip_harness_keys(request: Mapping[str, Any]) -> dict[str, Any]:
    """Remove `_`-prefixed harness-only keys from content blocks.

    `media.build_media_content_block` attaches `_local_path` so a provider that
    cannot transmit base64 can reference the file. The SDK rejects unknown keys
    inside a content block, so sending it would 400 — and it would 400 only on
    the media path, which is the path with the fewest fixtures. Stripping here
    rather than at the call site means a new provider cannot forget to do it.
    """
    payload = dict(request)
    messages = payload.get("messages")
    if not messages:
        return payload
    payload["messages"] = [
        {
            **message,
            "content": [
                {k: v for k, v in block.items() if not k.startswith("_")}
                if isinstance(block, Mapping)
                else block
                for block in message.get("content", ())
            ],
        }
        if isinstance(message, Mapping) and "content" in message
        else message
        for message in messages
    ]
    return payload


class Provider(Protocol):
    """Dispatch a built request. Classification stays in `transport.py`."""

    kind: str

    def dispatch(self, request: Mapping[str, Any]) -> Any:
        """Send the request and return a response object."""
        ...

    def count_tokens(self, request: Mapping[str, Any]) -> int | None:
        """Token count for preflight, or None when the provider cannot say."""
        ...


class AnthropicProvider:
    """The real API. The contract of record.

    Holds the SDK client and nothing else — streaming choice, retry, and budget
    all stay with `transport.Client`, so this class has no policy of its own.
    """

    kind = "anthropic"

    def __init__(self, client: Any, *, should_stream: bool = False) -> None:
        self._client = client
        self._should_stream = should_stream

    def dispatch(self, request: Mapping[str, Any]) -> Any:
        payload = _strip_harness_keys(request)
        if self._should_stream:
            with self._client.messages.stream(**payload) as stream:
                return stream.get_final_message()
        return self._client.messages.create(**payload)

    def count_tokens(self, request: Mapping[str, Any]) -> int | None:
        try:
            response = self._client.messages.count_tokens(
                model=request["model"],
                system=request.get("system", ""),
                messages=request["messages"],
            )
        except Exception:  # noqa: BLE001 - preflight must not block on itself
            return None
        return getattr(response, "input_tokens", None)


class ClaudeCliProvider:
    """The local `claude -p` binary. A development aid, NOT an equivalent.

    Why it exists: every fixture in `samples/` replays a hand-authored response,
    so nothing in the suite has ever been checked against a real model. That is a
    large gap, and closing it via the paid API on every iteration is expensive
    enough that it does not happen. This provider makes "does a real model behave
    like the fixture claims" a cheap question.

    **How it differs from the Anthropic path.** Every item here is a reason a
    green run under this provider does not certify the same thing:

    1. **No `output_config`, so no schema enforcement.** The wire schema is
       requested in prose and validated after the fact. The API guarantees a
       conforming response or a reject; this guarantees nothing, so a
       non-conforming answer surfaces as a parse failure rather than being
       impossible.
    2. **Fenced output.** Results arrive wrapped in a markdown code fence even
       when the prompt forbids it. Stripping it is this class's job, and a
       response needing a strip is a response the API would not have produced.
    3. **Media goes through a filesystem read, not a content block.** The CLI has
       no way to accept a base64 block, so an image reaches the model as a `Read`
       tool call against a path. Different mechanism, possibly different
       preprocessing. So this provider **cannot** validate the media content-block
       path — only whether a model can read the artifact at all.
    4. **It is an agent, not a single call.** `num_turns > 1` means tool use
       happened. Latency, cost, and token counts are not comparable to one API
       call, and the model may have taken actions between prompt and answer.
    5. **No `effort` control.** Depth is whatever the CLI chose. A spec declaring
       `effort: max` is silently ignored here.
    6. **Its own system prompt.** The CLI injects a large harness prompt (~37k
       cached tokens observed), so `SYSTEM_PROMPT` is not the only instruction in
       context. Prompt-sensitivity findings do not transfer.

    Because of 3 and 6 in particular, a response captured here is **not** a valid
    `recorded.json` for the Anthropic path. `provider_notes` records the
    divergences so a ledger line carries them.
    """

    kind = "claude_cli"

    def __init__(
        self,
        *,
        model: str = _CLI_DEFAULT_MODEL,
        binary: str = "claude",
        timeout_seconds: float = 180.0,
        allowed_tools: Sequence[str] = ("Read",),
        cwd: str | None = None,
    ) -> None:
        resolved = shutil.which(binary)
        if resolved is None:
            raise DependencyMissingError(
                f"the {binary!r} CLI is not on PATH, so provider 'claude_cli' "
                "cannot make a call. Install Claude Code or select provider "
                "'anthropic'."
            )
        self._binary = resolved
        self._model = model
        self._timeout = timeout_seconds
        self._allowed_tools = tuple(allowed_tools)
        self._cwd = cwd

    # -- prompt assembly ---------------------------------------------------

    def _flatten(self, request: Mapping[str, Any]) -> tuple[str, tuple[str, ...]]:
        """Collapse a Messages request into one prompt string.

        Returns the prompt and the notes describing what was lost. Media blocks
        become path references, which is divergence 3 — recorded, not hidden.
        """
        notes: list[str] = []
        parts: list[str] = []

        system = request.get("system")
        if system:
            parts.append(str(system))
            notes.append(
                "system prompt was concatenated into the user prompt; the CLI "
                "also injects its own harness system prompt"
            )

        for message in request.get("messages", ()):
            for block in message.get("content", ()):
                btype = block.get("type")
                if btype == "text":
                    parts.append(block["text"])
                elif btype in {"image", "document"}:
                    path = block.get("_local_path")
                    if path:
                        parts.append(
                            f"Read the {btype} at {path} and use its contents "
                            "as the source material above."
                        )
                        notes.append(
                            f"{btype} reached the model as a filesystem Read of "
                            f"{path}, NOT as a base64 content block"
                        )
                    else:
                        raise SpecError(
                            f"provider 'claude_cli' cannot send a {btype} block "
                            "without a local path. It has no way to transmit "
                            "base64 media; only file-backed media works here. "
                            "Use provider 'anthropic' to exercise the real "
                            "content-block path."
                        )

        schema = (
            request.get("output_config", {}).get("format", {}).get("schema")
        )
        if schema is not None:
            parts.append(
                "Return ONLY a JSON object conforming to this schema. No prose, "
                "no explanation, no markdown fence:\n"
                + json.dumps(schema, indent=2)
            )
            notes.append(
                "the wire schema was requested in prose; this provider has no "
                "output_config, so conformance is NOT enforced"
            )
        if request.get("output_config", {}).get("effort"):
            notes.append(
                f"declared effort {request['output_config']['effort']!r} was "
                "ignored; the CLI exposes no effort control"
            )
        return "\n\n".join(parts), tuple(notes)

    # -- dispatch ----------------------------------------------------------

    def dispatch(self, request: Mapping[str, Any]) -> ProviderResponse:
        prompt, notes = self._flatten(request)
        argv = [
            self._binary,
            "-p",
            prompt,
            "--model",
            self._model,
            "--output-format",
            "json",
        ]
        if self._allowed_tools:
            argv += ["--allowed-tools", *self._allowed_tools]

        try:
            completed = subprocess.run(  # noqa: S603 - argv is built here, no shell
                argv,
                capture_output=True,
                text=True,
                timeout=self._timeout,
                cwd=self._cwd,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise TransportExhaustedError(
                f"the claude CLI did not answer within {self._timeout:.0f}s"
            ) from exc

        if completed.returncode != 0:
            detail = (completed.stderr or completed.stdout or "").strip()
            first = detail.splitlines()[0] if detail else "no output"
            if "model" in first.lower() and "not" in first.lower():
                raise ModelNotFoundError(
                    f"the claude CLI rejected model {self._model!r}: {first}"
                )
            raise TransportExhaustedError(
                f"the claude CLI exited {completed.returncode}: {first}"
            )

        try:
            envelope = json.loads(completed.stdout)
        except json.JSONDecodeError as exc:
            raise TransportExhaustedError(
                "the claude CLI returned output that is not JSON, so the "
                "response envelope could not be read"
            ) from exc

        return self._to_response(envelope, notes)

    def _to_response(
        self, envelope: Mapping[str, Any], notes: Sequence[str]
    ) -> ProviderResponse:
        """Shape the CLI envelope like an SDK `Message`."""
        all_notes = list(notes)

        if envelope.get("is_error") or envelope.get("subtype") != "success":
            detail = str(envelope.get("result") or envelope.get("subtype") or "")
            raise TransportExhaustedError(
                f"the claude CLI reported failure: {detail[:200]}"
            )

        text = str(envelope.get("result", ""))
        fenced = _FENCE.search(text)
        if fenced:
            trailing = text[fenced.end():].strip()
            text = fenced.group(1)
            all_notes.append(
                "the response was wrapped in a markdown fence and was unwrapped "
                "here; the API's structured-output path never fences"
            )
            if trailing:
                # Real observed behaviour, not hypothetical: the model explained
                # its answer below the fence. Harmless once the block is
                # extracted, but worth recording — under output_config the model
                # cannot emit anything outside the JSON, so this response shape is
                # only reachable on this provider.
                all_notes.append(
                    f"{len(trailing)} chars of prose followed the fenced block "
                    "and were discarded; the API's structured path cannot emit "
                    "text outside the JSON"
                )

        turns = int(envelope.get("num_turns") or 1)
        if turns > 1:
            all_notes.append(
                f"the CLI took {turns} turns (tool use occurred); this was an "
                "agent loop, not a single model call"
            )

        usage_raw = envelope.get("usage") or {}
        usage = _Usage(
            input_tokens=int(usage_raw.get("input_tokens") or 0),
            output_tokens=int(usage_raw.get("output_tokens") or 0),
        )
        if usage_raw.get("cache_creation_input_tokens"):
            all_notes.append(
                "input_tokens excludes the CLI's cached harness prompt "
                f"({usage_raw['cache_creation_input_tokens']} cache-creation "
                "tokens), so token counts are not comparable to an API call"
            )

        # The CLI reports its own stop reason; map the one that matters.
        stop_reason = envelope.get("stop_reason") or "end_turn"

        model = None
        model_usage = envelope.get("modelUsage") or {}
        if model_usage:
            model = next(iter(model_usage))

        return ProviderResponse(
            stop_reason=stop_reason,
            model=model or self._model,
            content=[_TextBlock(text=text)],
            usage=usage,
            provider=self.kind,
            provider_notes=tuple(all_notes),
        )

    def count_tokens(self, request: Mapping[str, Any]) -> int | None:
        """Unavailable. Preflight falls back to the offline heuristic.

        Returning None rather than a guess is deliberate: the CLI's own cached
        harness prompt dominates its input count, so any number produced here
        would describe a different request than the one `estimate` is sizing.
        """
        return None


def build_provider(
    kind: str,
    *,
    client: Any | None = None,
    should_stream: bool = False,
    model: str | None = None,
    cwd: str | None = None,
) -> Provider:
    """Construct a provider, or reject an unknown kind."""
    if kind not in PROVIDER_KINDS:
        raise SpecError(
            f"unknown provider {kind!r}; expected one of {list(PROVIDER_KINDS)}"
        )
    if kind == "anthropic":
        if client is None:
            raise SpecError(
                "provider 'anthropic' needs an SDK client; none was supplied"
            )
        return AnthropicProvider(client, should_stream=should_stream)
    return ClaudeCliProvider(model=model or _CLI_DEFAULT_MODEL, cwd=cwd)

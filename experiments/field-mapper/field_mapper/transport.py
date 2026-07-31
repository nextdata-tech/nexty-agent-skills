"""Anthropic SDK call layer for the field mapper.

Layer-1, fixed by CONTRACT.md section 8. This module owns:

- the single place a model call is made (`Client`, deliberately private)
- budget preflight and per-call re-checking (`estimate`, `PreflightEstimate`)
- transport retry with backoff, distinct from validation retry
- systemic-failure classification: what BLOCKS versus what degrades to a
  row-level status

What this module does NOT own:

- wire-schema compilation (`schema.py`) — it receives compiled schema bytes
- range/enum/substring checking and validation retry (`validate.py`) — this
  module classifies transport outcomes only, and never decides `ok` versus
  `validation_failed`
- ledger writing (`ledger.py`) — this module returns the facts a ledger line
  needs and writes nothing

The API key is read once into the client and never written to a log line, an
error message, a record, a `repr`, or a returned dataclass.
"""

from __future__ import annotations

import json
import os
import random
import re
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Final

# ---------------------------------------------------------------------------
# Error taxonomy
# ---------------------------------------------------------------------------
# CONTRACT.md section 1 puts the exception taxonomy in `errors.py` so the
# raised-exception -> value_status mapping lives in exactly one place. This
# module imports it rather than defining any fallback: a local re-definition
# would produce two distinct classes with the same name, and
# `except CredentialMissing` in a caller would silently fail to catch the one
# raised here. There is no degraded mode worth that.

from .errors import (
    BudgetExceededError,
    CredentialMissingError,
    DependencyMissingError,
    FieldMapperError,
    ModelNotFoundError,
    RunCancelledError,
    SchemaRejectedError,
    SystemicError,
    TransportExhaustedError,
)
from .media import MediaInput, build_media_content_block
from .providers import build_provider

__all__ = [
    "DEFAULT_MODEL_ID",
    "AttemptOutcome",
    "BudgetLedger",
    "CallResult",
    "PreflightEstimate",
    "RunBudget",
    "TransportConfig",
    "estimate",
    "resolve_api_key",
]


# ---------------------------------------------------------------------------
# Fixed transport facts (CONTRACT.md section 8)
# ---------------------------------------------------------------------------

#: The model this contract fixes. It is a DEFAULT, not a constant: the spec's
#: `model` field is authoritative, because `mapper_spec_id` hashes it (spec.py
#: §5 step 3). A transport that ignored the spec's model would call one model
#: while the spec id claimed another — reviews would bind to a `mapper_spec_id`
#: that never described the run that produced them.
DEFAULT_MODEL_ID: Final = "claude-opus-5"

#: Effort levels above which `thinking: {"type": "disabled"}` is a 400 on this
#: model. Thinking is ON by default here (unlike Opus 4.8/4.7), and disabling it
#: is accepted only at effort `high` or lower.
_EFFORT_ORDER: Final = ("low", "medium", "high", "xhigh", "max")
_MAX_EFFORT_WITH_THINKING_DISABLED: Final = "high"

#: Model-id prefixes supporting the 4.6-generation reasoning controls:
#: `thinking: {"type": "adaptive"}` AND `output_config.effort`. Both arrived
#: together and both are a 400 on earlier models:
#:
#:   "adaptive thinking is not supported on this model"
#:   "This model does not support the effort parameter"
#:
#: Verified against the live API on `claude-haiku-4-5`, one knob at a time.
#: `output_config.format` (structured output) is NOT gated — it works on 4.5.
#:
#: Found the hard way: a live run on haiku failed every cell with schema_reject,
#: and the harness's own hint blamed JSON Schema keywords. The request never
#: reached the schema — it was refused on `thinking`, and then on `effort`.
#: Treating one model family's capabilities as universal is the defect; this
#: table makes the assumption explicit and checkable.
_REASONING_CONTROL_MODELS: Final = (
    "claude-opus-5",
    "claude-opus-4-8",
    "claude-opus-4-7",
    "claude-opus-4-6",
    "claude-sonnet-5",
    "claude-sonnet-4-6",
    "claude-fable-5",
    "claude-mythos-5",
)


@dataclass(frozen=True)
class ModelCapabilities:
    """The two reasoning leaves, kept SEPARATE.

    They arrived together on the 4.6 generation, which is why the harness
    originally carried one boolean for both — and that was wrong. Probed live:

        claude-haiku-4-5   thinking.supported=True (non-adaptive), effort=False
        claude-sonnet-5    thinking adaptive=True,                 effort=True

    So haiku accepts a `thinking` parameter but refuses `output_config.effort`,
    and one boolean cannot express that. It made the harness send effort to a
    model that 400s on it, or omit thinking from one that accepts it.
    """

    adaptive_thinking: bool
    effort: bool
    #: True when this came from the table rather than the API, so a caller can
    #: say which it trusted. A degraded run that never says it was degraded is
    #: the failure the probe exists to remove.
    from_table: bool = True

    @property
    def any_reasoning_control(self) -> bool:
        return self.adaptive_thinking or self.effort


def supports_reasoning_controls(model: str) -> bool:
    """Table-only fallback: does `model` plausibly take reasoning controls?

    Prefix match so dated snapshots (`claude-opus-5-20260114`) resolve to their
    family. An unknown model is assumed NOT to support them: a needless omission
    costs some reasoning depth, while a wrong inclusion costs a 400 on every
    single cell — which is the failure this exists to prevent.

    Kept as the NO-NETWORK path. `preflight` and dry runs must work with no SDK
    and no key, so the table cannot simply be deleted in favour of the probe.
    Prefer `capabilities_for()`, which uses this only when the API cannot answer.
    """
    return any(model.startswith(prefix) for prefix in _REASONING_CONTROL_MODELS)


def capabilities_from_table(model: str) -> ModelCapabilities:
    """Offline guess. Conflates the two leaves, because a prefix cannot see them."""
    known = supports_reasoning_controls(model)
    return ModelCapabilities(
        adaptive_thinking=known, effort=known, from_table=True
    )


def probe_capabilities(client: Any, model: str) -> ModelCapabilities | None:
    """Ask the Models API what `model` actually supports. None if it cannot say.

    One free request per run. Fixes the table's two structural defects: a model
    family the table does not name is silently degraded forever, and the two
    leaves are genuinely independent (see `ModelCapabilities`).

    Never raises. A probe failure must not block a run that would otherwise
    succeed — the table still answers, and the caller records which was used.
    """
    try:
        info = client.models.retrieve(model)
        caps = getattr(info, "capabilities", None)
        if caps is None:
            return None
        thinking = getattr(caps, "thinking", None)
        types = getattr(thinking, "types", None)
        adaptive = getattr(getattr(types, "adaptive", None), "supported", None)
        effort = getattr(getattr(caps, "effort", None), "supported", None)
        if adaptive is None and effort is None:
            return None
        return ModelCapabilities(
            adaptive_thinking=bool(adaptive),
            effort=bool(effort),
            from_table=False,
        )
    except Exception:  # noqa: BLE001 - a probe must never break the run
        return None

#: Retried with backoff. Everything else surfaces immediately rather than
#: burning budget: 400/401/403/404 are systemic and retrying cannot fix them.
_RETRYABLE_STATUS: Final = frozenset({408, 409, 429, 500, 502, 503, 504, 529})

#: Pricing per million tokens (input, output), for the preflight spend estimate
#: only. Never used for billing.
#:
#: Prefix-matched, longest prefix first, same shape and maintenance burden as
#: `_REASONING_CONTROL_MODELS`. Previously two Opus-only constants, so a haiku
#: spec was priced at 5x its real input rate and 5x its output rate — and the
#: `pricing_is_approximate` flag that exists to catch exactly that could not
#: fire, because the one call site that would have set it dropped `spec.model`
#: before constructing the config.
_USD_PER_MTOK: Final[tuple[tuple[str, float, float], ...]] = (
    ("claude-haiku-4-5", 1.00, 5.00),
    ("claude-haiku", 1.00, 5.00),
    ("claude-sonnet", 3.00, 15.00),
    ("claude-fable", 10.00, 50.00),
    ("claude-opus", 5.00, 25.00),
)

#: Unknown model: price at the most expensive KNOWN rate rather than refusing or
#: guessing low. Errs high, which is the estimator's one stated principle — an
#: underestimate lets a run start and blow the ceiling mid-population, which is
#: strictly worse than a refusal at preflight.
_USD_PER_MTOK_FALLBACK: Final = (
    max(r[1] for r in _USD_PER_MTOK),
    max(r[2] for r in _USD_PER_MTOK),
)


def rates_for(model: str) -> tuple[float, float, bool]:
    """(input $/Mtok, output $/Mtok, is_approximate) for a model id."""
    for prefix, rate_in, rate_out in _USD_PER_MTOK:
        if model.startswith(prefix):
            return rate_in, rate_out, False
    return _USD_PER_MTOK_FALLBACK[0], _USD_PER_MTOK_FALLBACK[1], True

#: Rough chars-per-token for the offline estimate. `count_tokens` is the
#: accurate path and `estimate()` uses it when a client is supplied; this
#: constant only backs the no-network preflight.
_CHARS_PER_TOKEN: Final = 3.5

#: PDF cost is PER PAGE, not per byte. The documented maxima are 3,000 text
#: tokens per page plus the per-page rasterisation, so a counted PDF is priced at
#: the ceiling and the figure errs high by construction.
#:
#: Byte-based pricing was the previous approach and it erred LOW on dense
#: documents — the one failure mode the estimator exists to prevent.
_PDF_TOKENS_PER_PAGE_TEXT: Final = 3_000
_PDF_TOKENS_PER_PAGE_IMAGE: Final = 4_800

#: Documented per-image cap at high resolution. Flat rather than byte-derived:
#: image cost scales with PIXELS (ceil(w/28) * ceil(h/28)), which the harness
#: cannot read without an image library, and a compressed 40 KB PNG can carry
#: far more pixels than an uncompressed 400 KB one.
_IMAGE_TOKENS_MAX: Final = 4_784

#: Matches a PDF page object: `/Type /Page` but NOT `/Type /Pages` (the tree
#: node). Tolerant of the whitespace variants real writers emit.
_PDF_PAGE_RE: Final = re.compile(rb"/Type\s*/Page(?![s])")


def count_pdf_pages(data: bytes) -> int | None:
    """Best-effort page count with the stdlib only. None when unknowable.

    Scans for uncompressed `/Type /Page` objects. That works on ordinary
    non-encrypted PDFs and returns **None** on the common real-world case where
    page objects live in a compressed object stream (`/ObjStm`) — which is
    correct behaviour, not a limitation to paper over: an unpriceable artifact
    must be reported as unpriceable rather than silently priced at zero pages.
    """
    if not data.startswith(b"%PDF-"):
        return None
    found = len(_PDF_PAGE_RE.findall(data))
    return found or None

#: Hard API ceilings. NOT YET ENFORCED — declared here so the numbers live in one
#: place, but no call site reads them, so an oversized request still discovers its
#: 413 mid-population. Enforcing the page limit needs a page count, which needs a
#: PDF library the venv does not have; enforcing the byte limit is straightforward
#: and simply is not wired up. Stated plainly because a constant that looks like a
#: guard and is not one is worse than an absent guard.
#: Both apply to the WHOLE request, not per document.
#:
#: PROVIDER-SPECIFIC. 32 MB is the first-party Claude API and Claude Platform on
#: AWS figure; Bedrock allows 20 MB and Google Cloud 30 MB. A payload sized against
#: the value below can therefore 413 on a platform the spec never named — a spec
#: pins a model, not a platform. Sizing to the tightest (20 MB) would refuse valid
#: first-party runs, so the honest fix is a declared target platform rather than a
#: single constant. Until then this is the 1P ceiling and nothing else.
_MAX_REQUEST_BYTES: Final = 32 * 1024 * 1024

#: Also conditional: 600 pages holds at a 1M-token context window, dropping to 100
#: below it. So it moves with the model, not just the platform.
_MAX_PDF_PAGES_PER_REQUEST: Final = 600


class AttemptOutcome(str, Enum):
    """The four transport outcomes of CONTRACT.md section 8.

    The fourth is the one that is easy to miss: a refusal is an HTTP 200 with
    empty or partial content. Code that reads `content[0]` unconditionally
    breaks there, and breaks silently.
    """

    SUCCESS = "success"
    #: 4xx/5xx/network after backoff.
    TRANSPORT_ERROR = "transport_error"
    #: HTTP 200 whose content will not parse, or `stop_reason == "max_tokens"`.
    #: Never salvaged as a partial answer.
    SCHEMA_REJECT = "schema_reject"
    #: `stop_reason == "refusal"`. Branch on `stop_reason`, never on
    #: `stop_details` — the latter may be null even on a refusal.
    REFUSAL = "refusal"


# ---------------------------------------------------------------------------
# Key resolution
# ---------------------------------------------------------------------------

_ENV_KEY_NAMES: Final = ("ANTHROPIC_API_KEY",)


def resolve_api_key(
    secrets: Mapping[str, Any] | None = None,
    *,
    secret_name: str = "anthropic_api_key",
    allow_env: bool = True,
) -> str:
    """Resolve the API key: secrets dict first, env fallback for the CLI.

    In a transform the key arrives through `.secrets([...])` in `spec.py`; the
    env fallback exists so `__main__.py` can run a canary outside a build.

    Raises `CredentialMissingError` — a SystemicError, so a missing key BLOCKS
    rather than landing a run of `error` rows.

    The key is returned to exactly one caller (`Client.__init__`) and is never
    logged, echoed into an error message, or stored on a dataclass. The
    exception below names the *source* that was missing, never a value.
    """
    if secrets:
        value = secrets.get(secret_name)
        if isinstance(value, str) and value.strip():
            return value.strip()

    if allow_env:
        for name in _ENV_KEY_NAMES:
            value = os.environ.get(name)
            if value and value.strip():
                return value.strip()

    env_hint = " or ".join(_ENV_KEY_NAMES)
    raise CredentialMissingError(
        f"No Anthropic API key. Bind it in spec.py via "
        f'.secrets(["{secret_name}"]) so the transform receives it, or export '
        f"{env_hint} for a CLI canary run. The mapper refuses to start rather "
        f"than land a population of unattempted cells."
    )


# ---------------------------------------------------------------------------
# SDK import guard
# ---------------------------------------------------------------------------


def _import_anthropic() -> Any:
    """Import the SDK, or raise an actionable BLOCKING error.

    `anthropic` is absent from the desktop venv today. Surfacing that as a bare
    `ModuleNotFoundError` traceback from inside a dlt resource is unreadable and
    — worse — invites a caller to catch `ImportError` and degrade to a row-level
    sentinel. A missing dependency is systemic: it means zero cells can be
    attempted, so it BLOCKS.
    """
    try:
        import anthropic  # noqa: PLC0415
    except ImportError as exc:
        raise DependencyMissingError(
            "The `anthropic` package is not installed, so the field mapper "
            "cannot make a single call.\n"
            "  Desktop: add `anthropic` to RUNTIME_DEP_PACKAGES in "
            "nxd-desktop-setup.sh and re-provision ~/.nxd/desktop-venv.\n"
            "  Ad-hoc:  uv pip install anthropic\n"
            "This blocks the build. It is never downgraded to a row-level "
            "status: with no SDK, every cell is unattempted, and landing that "
            "as data would report 0% coverage as a finding."
        ) from exc
    return anthropic


# ---------------------------------------------------------------------------
# Budget
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RunBudget:
    """Hard ceilings, aligned to the consent grant (design section 9/10).

    Exceeding any of these BLOCKS. `required_coverage` is what makes the
    mid-run check deterministic rather than a wait-until-the-money-runs-out
    failure: if the remaining budget cannot cover the cells still undispatched,
    the run stops now and the undispatched cells land `skipped`.
    """

    max_calls: int
    max_input_tokens: int
    max_output_tokens: int
    max_usd: float
    #: Wall-clock deadline for the whole run.
    max_wall_seconds: float
    #: Fraction of target cells that must be attempted for the build to be
    #: landable. 1.0 means "every cell or block".
    required_coverage: float = 1.0
    #: Bounded canary before the full population. 0 disables.
    canary_calls: int = 0

    def __post_init__(self) -> None:
        for name in (
            "max_calls",
            "max_input_tokens",
            "max_output_tokens",
            "max_usd",
            "max_wall_seconds",
        ):
            if getattr(self, name) <= 0:
                raise ValueError(f"RunBudget.{name} must be positive")
        if not 0.0 < self.required_coverage <= 1.0:
            raise ValueError("RunBudget.required_coverage must be in (0.0, 1.0]")
        if self.canary_calls < 0:
            raise ValueError("RunBudget.canary_calls must be >= 0")


@dataclass
class BudgetLedger:
    """Live consumption, re-checked before every call.

    Concurrency note (CONTRACT.md open question 2): `reserve()` decrements
    before dispatch rather than after completion, so N concurrent workers cannot
    collectively overshoot a ceiling that a serial check would have caught. The
    reservation is sized on the *estimate*; `record()` reconciles to actuals.
    """

    budget: RunBudget
    #: Which model's rates reconcile actuals. Empty falls back to the most
    #: expensive known rate — this governs the `max_usd` STOP, not just a
    #: printed estimate, so pricing a cheap model at Opus rates halts a run
    #: early and pricing an expensive one at haiku rates overshoots the ceiling
    #: the operator consented to.
    model: str = ""
    started_monotonic: float = field(default_factory=time.monotonic)
    calls_made: int = 0
    calls_reserved: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    usd_spent: float = 0.0

    @property
    def elapsed_seconds(self) -> float:
        return time.monotonic() - self.started_monotonic

    @property
    def calls_remaining(self) -> int:
        return max(0, self.budget.max_calls - max(self.calls_made, self.calls_reserved))

    @property
    def usd_remaining(self) -> float:
        return max(0.0, self.budget.max_usd - self.usd_spent)

    @property
    def seconds_remaining(self) -> float:
        return max(0.0, self.budget.max_wall_seconds - self.elapsed_seconds)

    def exhaustion_reason(self) -> str | None:
        """Name the first exhausted ceiling, or None. Never raises."""
        if self.calls_remaining <= 0:
            return (
                f"call ceiling reached ({self.budget.max_calls} calls)"
            )
        if self.input_tokens >= self.budget.max_input_tokens:
            return (
                f"input-token ceiling reached "
                f"({self.input_tokens} >= {self.budget.max_input_tokens})"
            )
        if self.output_tokens >= self.budget.max_output_tokens:
            return (
                f"output-token ceiling reached "
                f"({self.output_tokens} >= {self.budget.max_output_tokens})"
            )
        if self.usd_remaining <= 0.0:
            return f"spend ceiling reached (${self.budget.max_usd:.2f})"
        if self.seconds_remaining <= 0.0:
            return f"deadline reached ({self.budget.max_wall_seconds:.0f}s)"
        return None

    def check_can_cover(self, cells_remaining: int, calls_per_cell: int = 1) -> None:
        """Fail deterministically when the remaining budget cannot finish.

        Called before each dispatch. Raising here (rather than at exhaustion)
        is what turns "we ran out of money at 63%" into a decision the build
        makes on purpose. Undispatched cells become `skipped`, which blocks —
        a partial run must not be landable as a complete one.
        """
        reason = self.exhaustion_reason()
        if reason is not None:
            raise BudgetExceededError(
                f"Run budget exhausted before completing the population: "
                f"{reason}. {cells_remaining} cell(s) undispatched."
            )

        needed = cells_remaining * calls_per_cell
        coverable = self.calls_remaining
        if coverable < needed * self.budget.required_coverage:
            raise BudgetExceededError(
                f"Remaining budget cannot meet required coverage: "
                f"{coverable} call(s) left, {needed} needed for "
                f"{cells_remaining} remaining cell(s) at "
                f"{self.budget.required_coverage:.0%} coverage. Failing now "
                f"rather than landing a silently truncated run."
            )

    def reserve(self, calls: int = 1) -> None:
        self.calls_reserved += calls

    def release(self, calls: int = 1) -> None:
        self.calls_reserved = max(0, self.calls_reserved - calls)

    def record(self, *, input_tokens: int, output_tokens: int) -> None:
        """Reconcile a completed attempt to actuals."""
        self.calls_made += 1
        self.release(1)
        self.input_tokens += input_tokens
        self.output_tokens += output_tokens
        self.usd_spent += _usd_for(input_tokens, output_tokens, self.model)


def _usd_for(input_tokens: int, output_tokens: int, model: str = "") -> float:
    rate_in, rate_out, _ = rates_for(model)
    return input_tokens / 1_000_000 * rate_in + output_tokens / 1_000_000 * rate_out


@dataclass(frozen=True)
class PreflightEstimate:
    """What a run will cost, computed before the first call.

    `fits_within` is the gate: a run whose estimate exceeds the grant ceiling
    is refused at the boundary, not discovered mid-population.
    """

    cell_count: int
    calls_per_cell: int
    estimated_calls: int
    estimated_input_tokens: int
    estimated_output_tokens: int
    estimated_usd: float
    estimated_wall_seconds: float
    #: True when the estimate is anchored on `count_tokens`; False when it fell
    #: back to the offline character heuristic. Surfaced so a preflight report
    #: can say which it is rather than implying precision it does not have.
    token_counts_measured: bool
    #: The model whose rates produced `estimated_usd`, and the model the run
    #: will call. Surfaced because the price table is per-model: a spend figure
    #: is only meaningful next to the model it priced.
    model: str = DEFAULT_MODEL_ID
    #: True when `model` is not the one the price table describes, so
    #: `estimated_usd` is indicative rather than costed. A budget refusal says
    #: so instead of implying an exact figure.
    pricing_is_approximate: bool = False
    #: Media artifacts whose byte size this process could not read (url/file_id),
    #: so their token cost is excluded from the estimate entirely. Non-zero means
    #: `estimated_input_tokens` is a floor, not an estimate — a preflight report
    #: must say so rather than presenting a confident number.
    unsized_media: int = 0

    def fits_within(self, budget: RunBudget) -> list[str]:
        """Return the ceilings this estimate breaches. Empty means it fits."""
        breaches: list[str] = []
        if self.estimated_calls > budget.max_calls:
            breaches.append(
                f"calls: {self.estimated_calls} > {budget.max_calls}"
            )
        if self.estimated_input_tokens > budget.max_input_tokens:
            breaches.append(
                f"input tokens: {self.estimated_input_tokens} > "
                f"{budget.max_input_tokens}"
            )
        if self.estimated_output_tokens > budget.max_output_tokens:
            breaches.append(
                f"output tokens: {self.estimated_output_tokens} > "
                f"{budget.max_output_tokens}"
            )
        if self.estimated_usd > budget.max_usd:
            breaches.append(
                f"spend: ${self.estimated_usd:.2f} > ${budget.max_usd:.2f}"
            )
        if self.estimated_wall_seconds > budget.max_wall_seconds:
            breaches.append(
                f"wall time: {self.estimated_wall_seconds:.0f}s > "
                f"{budget.max_wall_seconds:.0f}s"
            )
        return breaches

    def require_within(self, budget: RunBudget) -> None:
        """Raise `BudgetExceededError` unless the estimate fits.

        This is the design's "fail the build when remaining budget cannot meet
        required coverage", evaluated before the first call.
        """
        breaches = self.fits_within(budget)
        if breaches:
            caveats = []
            if not self.token_counts_measured:
                caveats.append(
                    "token counts are the offline heuristic, not count_tokens"
                )
            if self.pricing_is_approximate:
                caveats.append(
                    f"spend is priced at {DEFAULT_MODEL_ID} rates but the run "
                    f"calls {self.model}"
                )
            caveat_text = f" (caveats: {'; '.join(caveats)})" if caveats else ""
            raise BudgetExceededError(
                "Preflight estimate exceeds the declared ceiling; refusing to "
                "start. Breaches: " + "; ".join(breaches) + caveat_text + ". "
                "Raise the grant ceiling deliberately, or reduce the "
                "population — do not start a run that cannot finish."
            )


# ---------------------------------------------------------------------------
# Transport configuration
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TransportConfig:
    """Per-spec transport knobs. Layer 2 sets these; Layer 1 enforces them.

    Build one with `from_spec()` rather than by hand wherever a `MapperSpec` is
    in scope — that is what keeps the model actually called identical to the
    model hashed into `mapper_spec_id`.
    """

    #: Exact model id. Mirrors `MapperSpec.model`, which is hashed into
    #: `mapper_spec_id`; `from_spec()` is the binding that keeps them equal.
    model: str = DEFAULT_MODEL_ID
    #: Depth. `budget_tokens` does not exist on this model. Default matches
    #: `MapperSpec.effort` so a hand-built config and a spec-derived one do not
    #: silently run at different depths.
    effort: str = "medium"
    #: Sized with explicit headroom over the schema's expected output: on this
    #: model `max_tokens` caps thinking PLUS response text, and thinking is on
    #: by default. A snug value truncates mid-object and surfaces as a parse
    #: failure that looks like a model defect.
    max_tokens: int = 16_000
    #: Stream above this, so a long generation cannot hit the request timeout.
    stream_above_max_tokens: int = 8_000
    #: Transport-retry budget. Distinct from `max_validation_retries`, which is
    #: `validate.py`'s and is never spent on a transport failure.
    max_transport_retries: int = 4
    backoff_base_seconds: float = 1.0
    backoff_max_seconds: float = 60.0
    #: Per-request timeout in seconds.
    request_timeout_seconds: float = 600.0
    #: Thinking is ON by default on this model. Disabling is legal only at
    #: effort `high` or below — see `_validate_thinking_effort_pairing`.
    thinking_enabled: bool = True
    #: `"omitted"` (default) or `"summarized"`.
    thinking_display: str = "omitted"

    def __post_init__(self) -> None:
        if not self.model or not self.model.strip():
            raise ValueError("TransportConfig.model must name a model")
        if self.effort not in _EFFORT_ORDER:
            raise ValueError(
                f"effort must be one of {_EFFORT_ORDER}, got {self.effort!r}"
            )
        if self.max_tokens <= 0:
            raise ValueError("max_tokens must be positive")
        if self.max_transport_retries < 0:
            raise ValueError("max_transport_retries must be >= 0")
        _validate_thinking_effort_pairing(
            model=self.model,
            effort=self.effort,
            thinking_enabled=self.thinking_enabled,
        )

    @classmethod
    def from_spec(cls, spec: Any, **overrides: Any) -> TransportConfig:
        """Derive the config from a landed `MapperSpec`.

        Takes `model` and `effort` from the spec so the call and the spec hash
        can never disagree. Everything else is a transport-only knob the spec
        does not declare, and stays overridable here.

        Typed as `Any` deliberately: importing `MapperSpec` would make
        `spec.py` -> `schema.py` -> `transport.py` a cycle, and this module
        needs only two attributes.
        """
        return cls(
            model=getattr(spec, "model", DEFAULT_MODEL_ID),
            effort=getattr(spec, "effort", "medium"),
            **overrides,
        )

    @property
    def should_stream(self) -> bool:
        return self.max_tokens > self.stream_above_max_tokens


def _validate_thinking_effort_pairing(
    *, model: str, effort: str, thinking_enabled: bool
) -> None:
    """Reject the one parameter pairing this model 400s on.

    On `claude-opus-5`, `thinking: {"type": "disabled"}` is accepted only at
    effort `high` or lower; pairing it with `xhigh`/`max` is a 400. Catching it
    at construction turns a mid-run systemic failure into a config error the
    caller sees before any credential is read.
    """
    if thinking_enabled:
        return
    cap = _EFFORT_ORDER.index(_MAX_EFFORT_WITH_THINKING_DISABLED)
    if _EFFORT_ORDER.index(effort) > cap:
        raise SchemaRejectedError(
            f"{model} rejects thinking_enabled=False at effort "
            f"{effort!r} with a 400: disabling thinking is accepted only at "
            f"{_MAX_EFFORT_WITH_THINKING_DISABLED!r} or below. Either leave "
            f"thinking on (the default on this model) or lower the effort."
        )


# ---------------------------------------------------------------------------
# Call result
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CallResult:
    """One attempt's outcome, carrying exactly what a ledger line needs.

    Deliberately carries no request payload and no API key: `input_hash` stands
    in for content, per CONTRACT.md section 9. At 10k x 1MB PDFs, verbatim
    logging is a second PII store.
    """

    outcome: AttemptOutcome
    #: Parsed JSON object, present only on SUCCESS.
    parsed: dict[str, Any] | None
    #: sha256 of the raw response text. Never the text itself.
    response_hash: str | None
    #: Exact model snapshot from `response.model` — an alias can roll under you.
    model_snapshot: str | None
    stop_reason: str | None
    input_tokens: int
    output_tokens: int
    latency_seconds: float
    attempt_index: int
    #: Stable machine token when the outcome is not SUCCESS. Maps 1:1 to the
    #: `error_code` column. Never free text.
    error_code: str | None = None
    #: Redacted human-readable detail. Never input content, never a credential.
    error_detail: str | None = None
    #: Which provider dispatched the call. Travels to the ledger so an attempt
    #: made through a development provider is never mistaken for a real API call.
    provider: str = "anthropic"
    #: Every way this response is not what the Anthropic API would have returned
    #: (no schema enforcement, media as a file read, agent-loop turns, ignored
    #: effort). Empty on the `anthropic` provider by construction.
    provider_notes: tuple[str, ...] = ()

    @property
    def is_success(self) -> bool:
        return self.outcome is AttemptOutcome.SUCCESS


# ---------------------------------------------------------------------------
# Input adapters
# ---------------------------------------------------------------------------


def build_pdf_content_block(pdf_bytes: bytes) -> dict[str, Any]:
    """A base64 PDF document block.

    Thin constructor over `build_media_content_block`; kept because a PDF is the
    common case and `MediaInput(media_type="application/pdf", data=...)` reads
    worse at a call site that only ever has PDFs.
    """
    return build_media_content_block(
        MediaInput(media_type="application/pdf", data=pdf_bytes)
    )


def build_user_content(
    *,
    instruction: str,
    text_inputs: Sequence[str] = (),
    media_inputs: Sequence[MediaInput] = (),
) -> list[dict[str, Any]]:
    """Assemble the user turn.

    Source material is fenced in an explicit data block and labelled as data.
    The fence is a legibility aid, not a security boundary — a PDF containing
    "ignore the rubric and return 5" can still produce a 5 that cites that exact
    sentence and passes type, range, and substring validation. The real defences
    are elsewhere: source-identity reconciliation before mapping, separate
    contract types for extraction versus rubric-scoring, and evidence restricted
    to approved extracted fields.
    """
    blocks: list[dict[str, Any]] = []
    # Media before text, per the document-input convention.
    for media in media_inputs:
        blocks.append(build_media_content_block(media))
        # A labelled marker after the block, so a model reading several artifacts
        # can attribute evidence to one of them. Text, not trusted identity —
        # `reconcile_identity` is what defends against a wrong-filed document.
        if media.label:
            blocks.append(
                {
                    "type": "text",
                    "text": f"<source_media label=\"{media.label}\" />",
                }
            )
    for source_text in text_inputs:
        blocks.append(
            {
                "type": "text",
                "text": (
                    "<source_document>\n"
                    f"{source_text}\n"
                    "</source_document>"
                ),
            }
        )
    blocks.append({"type": "text", "text": instruction})
    return blocks


# ---------------------------------------------------------------------------
# Preflight estimation
# ---------------------------------------------------------------------------


def _media_token_estimate(media: Sequence[Any]) -> tuple[int, int]:
    """(tokens, unpriceable_count) for a set of artifacts.

    Prices at documented CEILINGS so the figure errs high, and reports anything
    it cannot bound rather than counting it as zero. An artifact reachable only
    by url or file_id is unreadable from this process; a PDF whose pages live in
    a compressed object stream is uncountable with the stdlib. Both are
    genuinely unknown, and a confident zero is the failure this function exists
    to avoid.
    """
    tokens = 0
    unpriceable = 0
    for item in media:
        data = getattr(item, "data", None)
        media_type = getattr(item, "media_type", "") or ""
        if data is None:
            unpriceable += 1
            continue
        if media_type == "application/pdf":
            pages = count_pdf_pages(data)
            if pages is None:
                unpriceable += 1
                continue
            tokens += pages * (
                _PDF_TOKENS_PER_PAGE_TEXT + _PDF_TOKENS_PER_PAGE_IMAGE
            )
        elif media_type.startswith("image/"):
            # Flat documented cap: real cost is ceil(w/28) * ceil(h/28), and
            # reading dimensions needs an image library the venv lacks.
            tokens += _IMAGE_TOKENS_MAX
        else:
            unpriceable += 1
    return tokens, unpriceable


def estimate(
    *,
    cell_count: int,
    instruction: str,
    text_inputs: Sequence[str] = (),
    media_sizes_bytes: Sequence[int | None] = (),
    #: The artifacts themselves, when the caller holds them. Preferred over
    #: `media_sizes_bytes`: cost depends on PAGES (PDF) and PIXELS (image), and
    #: neither is derivable from a byte count. Falls back to the size list when
    #: absent, which prices every artifact as unsized.
    media: Sequence[Any] = (),
    config: TransportConfig | None = None,
    calls_per_cell: int = 1,
    expected_output_tokens: int | None = None,
    observed_latency_seconds: float = 2.0,
    concurrency: int = 1,
    client: Any | None = None,
) -> PreflightEstimate:
    """Estimate calls, tokens, spend, and wall time before the first call.

    Anchors on `count_tokens` when a client is supplied; falls back to an
    offline character heuristic otherwise, and says which via
    `token_counts_measured`. The heuristic errs high on purpose — an
    underestimate that lets a run start and then blows the ceiling at 60% is
    strictly worse than a refusal at preflight.

    `calls_per_cell` should carry the validation-retry budget the spec declares,
    not just 1. Sizing the ceiling on the happy path is how a run that retries
    normally still runs out of budget.
    """
    if cell_count < 0:
        raise ValueError("cell_count must be >= 0")
    if calls_per_cell < 1:
        raise ValueError("calls_per_cell must be >= 1")
    if concurrency < 1:
        raise ValueError("concurrency must be >= 1")

    cfg = config or TransportConfig()
    measured = False
    per_call_input: int

    if client is not None:
        try:
            counted = client.count_tokens(
                instruction=instruction, text_inputs=text_inputs
            )
        except FieldMapperError:
            raise
        except Exception:  # noqa: BLE001 - estimation must never block on itself
            counted = None
        if counted is not None:
            per_call_input = counted
            measured = True
        else:
            per_call_input = _offline_token_estimate(instruction, text_inputs)
    else:
        per_call_input = _offline_token_estimate(instruction, text_inputs)

    # Media is not visible to count_tokens without uploading it, so its cost is
    # always the heuristic. Additive to whichever text estimate we used.
    #
    # A `None` size is a url/file_id artifact this process cannot read, so its
    # token cost is genuinely unknown. Counting it as zero would produce a
    # confident underestimate, and an underestimate that lets a run start and
    # then blows the ceiling at 60% is strictly worse than a refusal. The count
    # is surfaced on the estimate so the caller reports "N artifact(s) unsized"
    # instead of implying full coverage.
    if media:
        media_tokens, unsized_media = _media_token_estimate(media)
    else:
        # No artifacts handed over: nothing can be priced, because neither page
        # count nor pixel count follows from a byte count. Every artifact is
        # unsized, which routes to the unpriced-refusal path rather than to a
        # confident wrong number.
        media_tokens = 0
        unsized_media = len(media_sizes_bytes)
    per_call_input += media_tokens

    # Thinking is on by default and is billed as output. Sizing the output
    # estimate on the JSON alone under-counts every call on this model.
    per_call_output = expected_output_tokens or cfg.max_tokens

    estimated_calls = cell_count * calls_per_cell
    total_input = estimated_calls * per_call_input
    total_output = estimated_calls * per_call_output
    wall = estimated_calls * observed_latency_seconds / concurrency

    return PreflightEstimate(
        cell_count=cell_count,
        calls_per_cell=calls_per_cell,
        estimated_calls=estimated_calls,
        estimated_input_tokens=total_input,
        estimated_output_tokens=total_output,
        estimated_usd=_usd_for(total_input, total_output, cfg.model),
        estimated_wall_seconds=wall,
        # An unsized artifact means part of the input was never counted at all,
        # so the total is not "measured" even when count_tokens answered for the
        # text half. Claiming measurement here would present a floor as a figure.
        token_counts_measured=measured and not unsized_media,
        model=cfg.model,
        # True when the model matched no known rate prefix and was priced at the
        # most expensive known rate. Previously `model != DEFAULT_MODEL_ID`,
        # which flagged every correctly-priced non-default model as approximate
        # and so trained the reader to ignore the flag.
        pricing_is_approximate=rates_for(cfg.model)[2],
        unsized_media=unsized_media,
    )


def _offline_token_estimate(
    instruction: str, text_inputs: Sequence[str]
) -> int:
    chars = len(instruction) + sum(len(t) for t in text_inputs)
    return int(chars / _CHARS_PER_TOKEN) + 512  # + fixed request overhead


# ---------------------------------------------------------------------------
# The client
# ---------------------------------------------------------------------------


class Client:
    """The single place a model call is made.

    NOT public (CONTRACT.md section 1): Layer 2 must not be able to make an
    unbudgeted, unledgered call. `map_inputs` owns the only instance.
    """

    def __init__(
        self,
        *,
        api_key: str | None = None,
        config: TransportConfig | None = None,
        budget_ledger: BudgetLedger | None = None,
        heartbeat: Callable[[str], None] | None = None,
        cancelled: Callable[[], bool] | None = None,
        sleep: Callable[[float], None] = time.sleep,
        provider: str = "anthropic",
        provider_model: str | None = None,
        provider_cwd: str | None = None,
    ) -> None:
        self._config = config or TransportConfig()
        self._ledger = budget_ledger
        # Progress signal so the supervisor readiness gate survives a long run.
        self._heartbeat = heartbeat or (lambda _msg: None)
        self._cancelled = cancelled or (lambda: False)
        self._sleep = sleep
        self._provider_kind = provider

        if provider == "anthropic":
            if not api_key:
                raise CredentialMissingError(
                    "provider 'anthropic' needs an API key; none was resolved. "
                    "Bind it via .secrets([...]) or export ANTHROPIC_API_KEY."
                )
            anthropic = _import_anthropic()
            self._anthropic = anthropic
            # The key lives inside the SDK client and nowhere else on `self`. It
            # is never assigned to an attribute, so it cannot reach a `repr` or a
            # pickle of this object.
            self._client = anthropic.Anthropic(
                api_key=api_key,
                timeout=self._config.request_timeout_seconds,
                # Our own backoff is the retry policy; the SDK's would double it
                # and make the transport-retry budget unauditable.
                max_retries=0,
            )
        else:
            # No SDK import and no key: the point of a non-Anthropic provider is
            # that it runs where neither is available.
            self._anthropic = None
            self._client = None

        self._provider = build_provider(
            provider,
            client=self._client,
            should_stream=self._config.should_stream,
            model=provider_model,
            cwd=provider_cwd,
        )
        #: Resolved lazily, once, on the first request. Not in __init__ so that
        #: constructing a Client stays free of network calls — `preflight` and
        #: the dry-run path build one and never dispatch.
        self._caps: ModelCapabilities | None = None

    def _capabilities(self) -> ModelCapabilities:
        """What this run's model actually supports. Probed once, then cached.

        Prefers the API's answer over the prefix table, and says so when they
        disagree. The table has two structural defects the probe removes: an
        unnamed model family is degraded silently and forever, and it collapses
        two genuinely independent leaves into one boolean — haiku-4-5 reports
        thinking supported with adaptive False and effort False, which the table
        cannot represent.

        Falls back to the table whenever the probe cannot answer: no SDK, no
        key, a non-Anthropic provider, or a Models API that does not know this
        model. A run must not fail because a capability lookup did.
        """
        if self._caps is not None:
            return self._caps
        table = capabilities_from_table(self._config.model)
        probed = (
            probe_capabilities(self._client, self._config.model)
            if self._client is not None
            else None
        )
        if probed is None:
            self._caps = table
            return self._caps
        if (probed.adaptive_thinking, probed.effort) != (
            table.adaptive_thinking,
            table.effort,
        ):
            # Loud, because a silent disagreement means the table is wrong and
            # every offline path (preflight, dry run) is still trusting it.
            self._heartbeat(
                f"capability table disagrees with the API for "
                f"{self._config.model}: table says adaptive="
                f"{table.adaptive_thinking} effort={table.effort}, API says "
                f"adaptive={probed.adaptive_thinking} effort={probed.effort} — "
                f"using the API. The table needs updating."
            )
        self._caps = probed
        return self._caps

    def __repr__(self) -> str:
        """Deliberately minimal: nothing here can carry the key."""
        return (
            f"<field_mapper.transport.Client provider={self._provider_kind} "
            f"model={self._config.model} effort={self._config.effort}>"
        )

    # -- token counting ---------------------------------------------------

    def count_tokens(
        self, *, instruction: str, text_inputs: Sequence[str] = ()
    ) -> int | None:
        """Measured input tokens, or None if the provider cannot say.

        Routed through the provider: the `claude_cli` provider returns None
        because its own cached harness prompt dominates its input count, so any
        figure would describe a different request than the one being sized.
        `estimate` then falls back to the offline heuristic and reports
        `token_counts_measured=False` rather than presenting a wrong number.
        """
        return self._provider.count_tokens(
            {
                "model": self._config.model,
                "messages": [
                    {
                        "role": "user",
                        "content": build_user_content(
                            instruction=instruction, text_inputs=text_inputs
                        ),
                    }
                ],
            }
        )

    # -- the call ---------------------------------------------------------

    def call(
        self,
        *,
        system_prompt: str,
        instruction: str,
        wire_schema: Mapping[str, Any],
        text_inputs: Sequence[str] = (),
        media_inputs: Sequence[MediaInput] = (),
        input_hash: str,
        cells_remaining: int = 0,
    ) -> CallResult:
        """Make one attempt, with transport retry and backoff.

        Returns a `CallResult` for every non-blocking outcome — including
        refusal, schema reject, and exhausted transport retries. Raises only for
        systemic failures, which BLOCK: auth, model-not-found, a schema the API
        rejected, budget exhaustion, and cancellation.

        Validation retry is NOT performed here. This layer never decides `ok`
        versus `validation_failed`; conflating the two budgets is how a
        transport outage gets papered over as a model error.
        """
        cfg = self._config
        self._raise_if_cancelled()

        if self._ledger is not None:
            self._ledger.check_can_cover(max(cells_remaining, 1))

        request = self._build_request(
            system_prompt=system_prompt,
            instruction=instruction,
            wire_schema=wire_schema,
            text_inputs=text_inputs,
            media_inputs=media_inputs,
        )

        last_transport_detail = "no attempt completed"
        for attempt_index in range(cfg.max_transport_retries + 1):
            self._raise_if_cancelled()
            if self._ledger is not None:
                if (reason := self._ledger.exhaustion_reason()) is not None:
                    raise BudgetExceededError(
                        f"Run budget exhausted mid-call: {reason}."
                    )
                self._ledger.reserve(1)

            started = time.monotonic()
            try:
                response = self._dispatch(request)
            except Exception as exc:  # noqa: BLE001 - classified immediately below
                if self._ledger is not None:
                    self._ledger.release(1)
                # Systemic classes re-raise from inside and never reach here.
                detail = self._classify_transport_exception(exc)
                last_transport_detail = detail
                if attempt_index < cfg.max_transport_retries:
                    delay = self._backoff_delay(attempt_index, exc)
                    self._heartbeat(
                        f"transport retry {attempt_index + 1}/"
                        f"{cfg.max_transport_retries} in {delay:.1f}s: {detail}"
                    )
                    self._sleep(delay)
                    continue
                return CallResult(
                    outcome=AttemptOutcome.TRANSPORT_ERROR,
                    parsed=None,
                    response_hash=None,
                    model_snapshot=None,
                    stop_reason=None,
                    input_tokens=0,
                    output_tokens=0,
                    latency_seconds=time.monotonic() - started,
                    attempt_index=attempt_index,
                    error_code=TransportExhaustedError.error_code,
                    error_detail=(
                        f"exhausted {cfg.max_transport_retries} transport "
                        f"retries: {detail}"
                    ),
                )

            latency = time.monotonic() - started
            usage_in, usage_out = _usage_of(response)
            if self._ledger is not None:
                self._ledger.record(
                    input_tokens=usage_in, output_tokens=usage_out
                )
            self._heartbeat(
                f"call ok in {latency:.1f}s "
                f"(in={usage_in} out={usage_out} hash={input_hash[:12]})"
            )
            return self._interpret(
                response,
                latency_seconds=latency,
                attempt_index=attempt_index,
                input_tokens=usage_in,
                output_tokens=usage_out,
            )

        # Unreachable: the loop always returns or raises.
        raise TransportExhaustedError(last_transport_detail)

    # -- request construction --------------------------------------------

    def _build_request(
        self,
        *,
        system_prompt: str,
        instruction: str,
        wire_schema: Mapping[str, Any],
        text_inputs: Sequence[str],
        media_inputs: Sequence[MediaInput],
    ) -> dict[str, Any]:
        cfg = self._config
        # `format` is ungated — structured output works on 4.5-generation models.
        # `effort` is not: it is a 400 there, so it is added only where supported.
        output_config: dict[str, Any] = {
            "format": {"type": "json_schema", "schema": dict(wire_schema)},
        }
        caps = self._capabilities()
        if caps.effort:
            output_config["effort"] = cfg.effort
        request: dict[str, Any] = {
            "model": cfg.model,
            "max_tokens": cfg.max_tokens,
            # System carries ONLY harness-authored instruction. No source
            # content is ever interpolated here.
            "system": system_prompt,
            "messages": [
                {
                    "role": "user",
                    "content": build_user_content(
                        instruction=instruction,
                        text_inputs=text_inputs,
                        media_inputs=media_inputs,
                    ),
                }
            ],
            "output_config": output_config,
        }
        # No temperature / top_p / top_k: rejected with 400 on this model, and
        # rejected by design review independently. They never guaranteed
        # determinism. Do not add them back.
        if cfg.thinking_enabled and caps.adaptive_thinking:
            request["thinking"] = {
                "type": "adaptive",
                "display": cfg.thinking_display,
            }
        elif cfg.thinking_enabled:
            # Thinking wanted, adaptive unavailable. Omitting `thinking`
            # entirely is the correct default — the alternative,
            # `budget_tokens`, would need a budget this layer has no basis to
            # choose, and a wrong one truncates mid-object.
            #
            # NOTE this is where the two leaves genuinely diverge: haiku-4-5
            # reports thinking.supported=True with adaptive=False, so it would
            # accept a non-adaptive thinking block. Sending one is left for a
            # deliberate change rather than inferred here, because picking the
            # budget is exactly the decision this branch refuses to guess at.
            pass
        elif caps.adaptive_thinking:
            # Legal only at effort <= high; enforced in TransportConfig.
            request["thinking"] = {"type": "disabled"}
        # else: a pre-4.6 model has no `thinking` block at all. Sending
        # {"type": "disabled"} there is the same 400 as sending "adaptive" —
        # the parameter itself is unknown, not just that one value.
        return request

    def _dispatch(self, request: Mapping[str, Any]) -> Any:
        """Hand the built request to the provider.

        Everything above this line — the wire shape, budget accounting, retry
        policy, outcome classification — is provider-independent by design, so a
        development provider is governed by the same failure policy as the API.
        """
        return self._provider.dispatch(request)

    # -- outcome interpretation ------------------------------------------

    def _interpret(
        self,
        response: Any,
        *,
        latency_seconds: float,
        attempt_index: int,
        input_tokens: int,
        output_tokens: int,
    ) -> CallResult:
        """Map an HTTP 200 to one of the three non-transport outcomes."""
        stop_reason = getattr(response, "stop_reason", None)
        model_snapshot = getattr(response, "model", None)

        def _result(
            outcome: AttemptOutcome,
            *,
            parsed: dict[str, Any] | None = None,
            response_hash: str | None = None,
            error_code: str | None = None,
            error_detail: str | None = None,
        ) -> CallResult:
            return CallResult(
                outcome=outcome,
                parsed=parsed,
                response_hash=response_hash,
                model_snapshot=model_snapshot,
                stop_reason=stop_reason,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                latency_seconds=latency_seconds,
                attempt_index=attempt_index,
                error_code=error_code,
                error_detail=error_detail,
                # Carried from the provider's response so the ledger records
                # WHICH provider answered. Absent on a real SDK Message, where
                # the "anthropic" default is correct by construction.
                provider=getattr(response, "provider", "anthropic"),
                provider_notes=tuple(
                    getattr(response, "provider_notes", ()) or ()
                ),
            )

        # Branch on stop_reason, never on stop_details: the latter may be null
        # even on a refusal. A refusal is an HTTP 200 with empty or partial
        # content, so reading content[0] first would break here — silently.
        if stop_reason == "refusal":
            category = None
            details = getattr(response, "stop_details", None)
            if details is not None:
                category = getattr(details, "category", None)
            return _result(
                AttemptOutcome.REFUSAL,
                error_code="refusal",
                error_detail=(
                    f"model declined (category={category or 'unspecified'})"
                ),
            )

        if stop_reason == "max_tokens":
            # Never salvaged as a partial answer: a truncated JSON object that
            # happens to parse is a wrong answer, not a short one.
            return _result(
                AttemptOutcome.SCHEMA_REJECT,
                error_code=SchemaRejectedError.error_code,
                error_detail=(
                    f"response truncated at max_tokens="
                    f"{self._config.max_tokens}; thinking and text share this "
                    f"ceiling on {self._config.model}. Raise max_tokens — do "
                    f"not treat the partial object as an answer."
                ),
            )

        text = _first_text_block(response)
        if text is None:
            return _result(
                AttemptOutcome.SCHEMA_REJECT,
                error_code=SchemaRejectedError.error_code,
                error_detail=(
                    f"no text content block (stop_reason={stop_reason!r})"
                ),
            )

        response_hash = _sha256_hex(text)
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError as exc:
            return _result(
                AttemptOutcome.SCHEMA_REJECT,
                response_hash=response_hash,
                error_code=SchemaRejectedError.error_code,
                # Position only — never the payload, which is model output over
                # untrusted source text.
                error_detail=f"structured output did not parse at char {exc.pos}",
            )

        if not isinstance(parsed, dict):
            return _result(
                AttemptOutcome.SCHEMA_REJECT,
                response_hash=response_hash,
                error_code=SchemaRejectedError.error_code,
                error_detail=(
                    f"structured output was {type(parsed).__name__}, expected "
                    f"a JSON object"
                ),
            )

        return _result(
            AttemptOutcome.SUCCESS, parsed=parsed, response_hash=response_hash
        )

    # -- failure classification ------------------------------------------

    def _classify_transport_exception(self, exc: Exception) -> str:
        """Raise for systemic classes; return a redacted detail for retryables.

        This is the boundary the whole typed-failure policy rests on. Anything
        that will fail identically on every remaining cell must escape as a
        `SystemicError` and block the build. Only genuinely per-attempt
        failures are allowed to become a row-level `error`.
        """
        anthropic = self._anthropic

        if isinstance(exc, FieldMapperError):
            raise exc

        auth_error = getattr(anthropic, "AuthenticationError", ())
        if auth_error and isinstance(exc, auth_error):
            raise CredentialMissingError(
                "Anthropic rejected the API key (401). This blocks the build: "
                "the same key would fail on every remaining cell. Check the "
                "`.secrets([...])` binding in spec.py."
            ) from exc

        permission_error = getattr(anthropic, "PermissionDeniedError", ())
        if permission_error and isinstance(exc, permission_error):
            raise CredentialMissingError(
                f"The API key lacks permission for {self._config.model} (403). This "
                f"blocks the build — it is a systemic entitlement problem, not "
                f"a property of any row."
            ) from exc

        not_found_error = getattr(anthropic, "NotFoundError", ())
        if not_found_error and isinstance(exc, not_found_error):
            raise ModelNotFoundError(
                f"Model {self._config.model!r} was not found (404). This blocks the "
                f"build: every cell would fail identically."
            ) from exc

        bad_request_error = getattr(anthropic, "BadRequestError", ())
        if bad_request_error and isinstance(exc, bad_request_error):
            raise SchemaRejectedError(
                "The API rejected the request (400). This blocks the build: "
                "the compiled wire schema or a request parameter is invalid, "
                "so it will reject every cell. Common causes on "
                f"{self._config.model}: an unsupported JSON Schema keyword "
                "(`minimum`/`maximum`/`minLength` are not supported — route "
                "those to validate.py), or thinking disabled above `high` "
                f"effort. Redacted detail: {_redact_status(exc)}"
            ) from exc

        status = getattr(exc, "status_code", None)
        if isinstance(status, int) and status not in _RETRYABLE_STATUS:
            if 400 <= status < 500:
                raise SchemaRejectedError(
                    f"Non-retryable client error {status} from the API. This "
                    f"blocks the build rather than burning the transport-retry "
                    f"budget on a request that cannot succeed."
                ) from exc

        return _redact_status(exc)

    def _backoff_delay(self, attempt_index: int, exc: Exception) -> float:
        """Exponential backoff with jitter, honouring `retry-after`."""
        cfg = self._config
        retry_after = _retry_after_seconds(exc)
        if retry_after is not None:
            return min(retry_after, cfg.backoff_max_seconds)
        raw = cfg.backoff_base_seconds * (2**attempt_index)
        # Full jitter: synchronised retries across concurrent workers are how a
        # 429 turns into a thundering herd that keeps re-triggering itself.
        return min(raw, cfg.backoff_max_seconds) * (0.5 + random.random() / 2)

    def _raise_if_cancelled(self) -> None:
        if self._cancelled():
            raise RunCancelledError(
                "Run cancelled. Undispatched cells land `skipped`, which "
                "blocks the build — a cancelled run must not be landable as a "
                "complete one."
            )


# ---------------------------------------------------------------------------
# Response helpers
# ---------------------------------------------------------------------------


def _first_text_block(response: Any) -> str | None:
    """The first text block, or None.

    Never indexes `content[0]`: on a refusal the list is empty, and with
    thinking on the first block may be a thinking block rather than text.
    """
    content = getattr(response, "content", None) or []
    for block in content:
        if getattr(block, "type", None) == "text":
            text = getattr(block, "text", None)
            if isinstance(text, str) and text.strip():
                return text
    return None


def _usage_of(response: Any) -> tuple[int, int]:
    usage = getattr(response, "usage", None)
    if usage is None:
        return 0, 0
    return (
        int(getattr(usage, "input_tokens", 0) or 0),
        int(getattr(usage, "output_tokens", 0) or 0),
    )


def _retry_after_seconds(exc: Exception) -> float | None:
    response = getattr(exc, "response", None)
    headers = getattr(response, "headers", None)
    if headers is None:
        return None
    try:
        raw = headers.get("retry-after")
    except Exception:  # noqa: BLE001 - header access must never mask the error
        return None
    if raw is None:
        return None
    try:
        return max(0.0, float(raw))
    except (TypeError, ValueError):
        return None


def _redact_status(exc: Exception) -> str:
    """A ledger/error-safe description of a transport failure.

    Type name and status code only. An SDK exception's `message` can echo the
    request body, which would put source content — and in the worst case a
    credential — into a log line and a landed `error_detail`.
    """
    status = getattr(exc, "status_code", None)
    name = type(exc).__name__
    return f"{name}(status={status})" if status is not None else name


def _sha256_hex(text: str) -> str:
    import hashlib  # noqa: PLC0415

    return hashlib.sha256(text.encode("utf-8")).hexdigest()

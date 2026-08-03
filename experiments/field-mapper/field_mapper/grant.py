"""Consent-grant load and match. CONTRACT.md §9, design §9.

Split out of `__main__.py` for one reason: the check must happen **before** any
source content or credential is read, and an in-process caller
(`nxd-run-job-loop` invoking `map()` directly, which is the stated Layer-1 use)
must not be able to bypass it. A gate that lives in the CLI is not a gate.

**This is a userland convention, not an enforceable security boundary.** Nothing
in the spec or runtime can refuse a mapper — a determined caller can import
`transport` directly. Saying so plainly here is deliberate: describing this as a
security control would be false, and the Phase-D self-check is what actually
fails a closure that maps without a matching grant.

Pure stdlib.
"""

from __future__ import annotations

import datetime as _dt
import json
from dataclasses import dataclass, field as dc_field
from pathlib import Path
from typing import Any, Mapping, Sequence

from .errors import GrantError
from .spec import MapperSpec

__all__ = ["Grant", "PII_CATEGORIES"]

#: Declared PII exposure. Not enforced by inspection — the grant records what
#: the *user consented to*, and the Phase-D check compares it against what the
#: closure actually reads.
PII_CATEGORIES: frozenset[str] = frozenset(
    {"none", "pseudonymous", "personal", "sensitive"}
)


def _parse_expiry(raw: Any) -> _dt.datetime | None:
    if raw is None:
        return None
    if isinstance(raw, _dt.datetime):
        return raw if raw.tzinfo else raw.replace(tzinfo=_dt.timezone.utc)
    try:
        parsed = _dt.datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except ValueError as exc:
        raise GrantError(
            f"grant expiry {raw!r} is not an ISO-8601 timestamp"
        ) from exc
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=_dt.timezone.utc)


@dataclass(frozen=True)
class Grant:
    """A machine-readable consent grant, bound to a canonical `mapper_spec_id`.

    Binding to the spec hash rather than to a spec *name* is what makes the
    grant meaningful: editing the rubric produces a new `mapper_spec_id`, so the
    old grant stops matching and the user is asked again. A name-bound grant
    would silently authorize an instruction the user never saw.
    """

    #: The exact spec this grant authorizes. Never a name, never a glob.
    mapper_spec_id: str
    provider: str
    model: str
    #: The SECOND model, when the spec declares corroboration. Consent is
    #: per-model: a user who approved sending an artifact to one provider's
    #: model has not thereby approved sending it to another. Empty means the
    #: grant authorizes no corroborator, and a spec declaring one is refused.
    corroboration_model: str = ""
    purpose: str = ""
    #: Input fields and document classes the user consented to expose.
    input_fields: tuple[str, ...] = ()
    document_classes: tuple[str, ...] = ()
    pii_category: str = "none"
    recurring: bool = False
    expires_at: _dt.datetime | None = None
    #: Ceilings. `None` means the grant declares no ceiling on that axis.
    max_calls: int | None = None
    max_tokens: int | None = None
    max_usd: float | None = None
    granted_by: str = ""
    granted_at: str = ""
    source_path: str | None = dc_field(default=None, compare=False)

    def __post_init__(self) -> None:
        if not self.mapper_spec_id:
            raise GrantError(
                "grant declares no mapper_spec_id, so it authorizes nothing in "
                "particular. Bind the grant to a canonical spec hash."
            )
        if self.pii_category not in PII_CATEGORIES:
            raise GrantError(
                f"unknown pii_category {self.pii_category!r}; expected one of "
                f"{sorted(PII_CATEGORIES)}"
            )
        if not self.purpose.strip():
            raise GrantError(
                "grant declares no purpose. A grant without a stated purpose "
                "cannot be reviewed by the person who granted it."
            )

    # -- loading ------------------------------------------------------------

    @classmethod
    def load(cls, path: str | Path) -> "Grant":
        p = Path(path)
        try:
            raw = json.loads(p.read_text(encoding="utf-8"))
        except FileNotFoundError as exc:
            raise GrantError(
                f"no consent grant at {p}. The harness refuses to read source "
                "content or credentials without one."
            ) from exc
        except json.JSONDecodeError as exc:
            raise GrantError(f"grant at {p} is not valid JSON: {exc}") from exc
        grant = cls.from_dict(raw)
        object.__setattr__(grant, "source_path", str(p))
        return grant

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> "Grant":
        known = {
            "mapper_spec_id", "provider", "model", "corroboration_model",
            "purpose", "input_fields",
            "document_classes", "pii_category", "recurring", "expires_at",
            "max_calls", "max_tokens", "max_usd", "granted_by", "granted_at",
        }
        unknown = sorted(set(raw) - known)
        if unknown:
            raise GrantError(
                f"unknown key(s) in grant: {unknown!r}. Rejected rather than "
                "ignored — a typo'd ceiling key is a ceiling that does not exist."
            )
        for required in ("mapper_spec_id", "provider", "model", "purpose"):
            if required not in raw:
                raise GrantError(f"grant is missing required key {required!r}")
        return cls(
            mapper_spec_id=str(raw["mapper_spec_id"]),
            provider=str(raw["provider"]),
            model=str(raw["model"]),
            corroboration_model=str(raw.get("corroboration_model", "")),
            purpose=str(raw["purpose"]),
            input_fields=tuple(raw.get("input_fields", ())),
            document_classes=tuple(raw.get("document_classes", ())),
            pii_category=str(raw.get("pii_category", "none")),
            recurring=bool(raw.get("recurring", False)),
            expires_at=_parse_expiry(raw.get("expires_at")),
            max_calls=raw.get("max_calls"),
            max_tokens=raw.get("max_tokens"),
            max_usd=raw.get("max_usd"),
            granted_by=str(raw.get("granted_by", "")),
            granted_at=str(raw.get("granted_at", "")),
        )

    # -- the gate -----------------------------------------------------------

    def check(
        self,
        spec: MapperSpec,
        *,
        input_fields: Sequence[str] = (),
        document_classes: Sequence[str] = (),
        now: _dt.datetime | None = None,
    ) -> None:
        """Raise `GrantError` unless this grant authorizes this exact run.

        Call this BEFORE reading source content and BEFORE resolving the API
        key. Every mismatch is reported at once rather than one per call, so a
        user fixing a grant sees the whole delta instead of playing whack-a-mole.
        """
        problems: list[str] = []

        actual_id = spec.mapper_spec_id
        if self.mapper_spec_id != actual_id:
            problems.append(
                f"spec hash mismatch: grant authorizes {self.mapper_spec_id}, "
                f"this spec is {actual_id}. The rubric, fields, thresholds, or "
                "model changed since consent was given — which is exactly when "
                "the user should be asked again."
            )

        if self.model != spec.model:
            problems.append(
                f"model mismatch: grant authorizes {self.model!r}, spec names "
                f"{spec.model!r}"
            )

        # Consent is PER MODEL. Approving an artifact for one model is not
        # approval to send it to a second one, so a corroborating run under a
        # grant that does not name the corroborator refuses — the same shape as
        # the primary-model mismatch above, which demonstrably fires live.
        if spec.corroboration_model != self.corroboration_model:
            problems.append(
                f"corroboration model mismatch: grant authorizes "
                f"{self.corroboration_model or 'none'!r}, spec names "
                f"{spec.corroboration_model or 'none'!r}. Sending the artifact "
                f"to a second model is a separate disclosure and needs its own "
                f"consent."
            )

        moment = now or _dt.datetime.now(_dt.timezone.utc)
        if self.expires_at is not None and moment > self.expires_at:
            problems.append(
                f"grant expired at {self.expires_at.isoformat()} "
                f"(now {moment.isoformat()})"
            )

        # Undeclared inputs are the leak that matters: a grant listing three
        # fields does not authorize sending a fourth.
        if self.input_fields:
            undeclared = sorted(set(input_fields) - set(self.input_fields))
            if undeclared:
                problems.append(
                    f"input fields {undeclared} are not covered by the grant, "
                    f"which lists {sorted(self.input_fields)}"
                )
        if self.document_classes:
            undeclared_docs = sorted(
                set(document_classes) - set(self.document_classes)
            )
            if undeclared_docs:
                problems.append(
                    f"document classes {undeclared_docs} are not covered by the "
                    f"grant, which lists {sorted(self.document_classes)}"
                )

        if problems:
            raise GrantError(
                "consent grant does not authorize this run; refusing before "
                "reading source content or credentials.\n  - "
                + "\n  - ".join(problems)
            )

    def budget_ceilings(self) -> dict[str, Any]:
        """The grant's ceilings, for aligning `RunBudget` to consent.

        A run whose preflight estimate exceeds these is refused before the first
        call — the grant is the authority on spend, not the spec.
        """
        return {
            "max_calls": self.max_calls,
            "max_tokens": self.max_tokens,
            "max_usd": self.max_usd,
        }

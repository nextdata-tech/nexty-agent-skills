"""Judge-only check sets, keyed by discriminator.

Two authoring surfaces, one data shape:

* ``checks(answer=[...], clarify=[...], abstain=[...])`` — the flat builder from
  the stable public API. Returns ``{discriminator: [check strings]}``.
* ``checks.answer(...)`` / ``checks.clarify(...)`` / ``checks.abstain(...)`` —
  per-discriminator constructors that return the same single-key dict, so a
  suite author can compose them.

A "check" is a natural-language assertion the judge evaluates — the text of the
``checks[]`` entries in a public scenario's ``checks.json``. It is NEVER shown to
the agent; it lives on the judge side only.

Back-compat: ``load_checks_json`` reads an existing untyped
``evals/public/*/checks.json`` (``{name, checks: [{id, check}]}``) and lowers
every entry into ONE ``judge`` check bucket — those legacy files predate the
answer/clarify/abstain split, so all their checks route to the model judge.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

# Discriminator buckets a typed check set may carry, plus the catch-all "judge"
# bucket the untyped back-compat loader fills.
ANSWER = "answer"
CLARIFY = "clarify"
ABSTAIN = "abstain"
JUDGE = "judge"


def _clean(items: list[str] | None) -> list[str]:
    return [s for s in (items or []) if s]


def checks(
    *,
    answer: list[str] | None = None,
    clarify: list[str] | None = None,
    abstain: list[str] | None = None,
) -> dict[str, list[str]]:
    """Build a judge-only check set keyed by discriminator.

    Empty/absent buckets are dropped so ``checks()`` yields ``{}`` and a suite
    with only ``answer`` checks does not carry empty ``clarify`` / ``abstain``
    keys.
    """
    out: dict[str, list[str]] = {}
    for key, val in ((ANSWER, answer), (CLARIFY, clarify), (ABSTAIN, abstain)):
        cleaned = _clean(val)
        if cleaned:
            out[key] = cleaned
    return out


def _answer(*items: str) -> dict[str, list[str]]:
    """Checks that apply to ``answer`` cases (deterministic-EX side context)."""
    return checks(answer=list(items))


def _clarify(*items: str) -> dict[str, list[str]]:
    """Checks that apply to ``clarify`` cases (must ask, not silently pick)."""
    return checks(clarify=list(items))


def _abstain(*items: str) -> dict[str, list[str]]:
    """Checks that apply to ``abstain`` cases (must refuse, not fabricate)."""
    return checks(abstain=list(items))


def _judge(*items: str) -> dict[str, list[str]]:
    """Untyped checks routed to the model judge (the back-compat bucket)."""
    return {JUDGE: _clean(list(items))} if _clean(list(items)) else {}


def merge(*sets: dict[str, list[str]]) -> dict[str, list[str]]:
    """Merge several check sets, concatenating per-discriminator lists."""
    out: dict[str, list[str]] = {}
    for s in sets:
        for key, items in s.items():
            out.setdefault(key, []).extend(items)
    return out


def load_checks_json(path: str | Path) -> dict[str, list[str]]:
    """Back-compat: lower an untyped ``checks.json`` into ONE ``judge`` bucket.

    The legacy file shape is ``{name?, checks: [{id, check}]}`` (see any
    ``evals/public/*/checks.json``). Those entries are untyped free-text
    assertions with no answer/clarify/abstain discriminator, so every one routes
    to the model judge. The ``id`` is preserved by prefixing it onto the check
    text (``"<id>: <check>"``) so the judge report can cite the original check.
    """
    doc = json.loads(Path(path).read_text())
    entries: list[dict[str, Any]] = doc.get("checks", [])
    texts: list[str] = []
    for e in entries:
        cid = e.get("id")
        text = e.get("check", "")
        texts.append(f"{cid}: {text}" if cid else text)
    return _judge(*texts)


# Expose the per-discriminator constructors as attributes on ``checks`` so both
# ``checks(answer=[...])`` and ``checks.answer(...)`` author the same shape.
checks.answer = _answer  # type: ignore[attr-defined]
checks.clarify = _clarify  # type: ignore[attr-defined]
checks.abstain = _abstain  # type: ignore[attr-defined]
checks.judge = _judge  # type: ignore[attr-defined]
checks.merge = merge  # type: ignore[attr-defined]
checks.load_json = load_checks_json  # type: ignore[attr-defined]

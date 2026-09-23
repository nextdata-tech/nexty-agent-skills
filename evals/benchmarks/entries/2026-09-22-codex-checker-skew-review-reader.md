---
id: 2026-09-22-codex-checker-skew-review-reader
date: 2026-09-22
label: "detect retained self-checker skew and harden review-reader paths"
plugin_version: 0.52.2
status: NO_EVAL
scenarios: []
record: null
---
# Benchmark — detect retained self-checker skew and harden review-reader paths

## Notes

Harness-only. No scenario arm distinguishes the live Codex capture fingerprint
contract or the runner-owned review-reader path contract. This entry is separate
from `2026-09-22-redacted-review-evidence`: that entry covers recovering review
evidence when prompts are redacted; this one covers comparing the staged and
retained `self_check.py` and preserving exact allowlisted path spellings while
rejecting unsafe reader paths. The skew check covers only `self_check.py`; it
does not detect drift in other embedded helpers. Comparison markers retain only
a schema, status, and (when comparable) the two SHA-256 digests.

## Evidence

- `evals/dp-scenarios/tests/test_runner_codex_adapter.py` — automatic capture
  markers, byte equality/mismatch, no-follow reads, file-type checks, and the
  fail-closed size limit without requiring a reader-tool call.
- `evals/dp-scenarios/tests/test_runner_tier.py` — strict marker validation,
  required markers for applicable live Codex captures, replay compatibility,
  and mismatch-over-unreadable invalidation precedence.
- `evals/tests/test_desktop_stdio.py` — lexical path rejection, symlink escape
  filtering, and allowlisted-root spelling in reader responses.

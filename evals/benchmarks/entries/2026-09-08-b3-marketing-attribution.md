---
id: 2026-09-08-b3-marketing-attribution
date: 2026-09-08
label: "B3 safe marketing-attribution scenario"
plugin_version: 0.45.0
status: NO_EVAL
scenarios: []
record: null
---
# Benchmark — B3 safe marketing-attribution scenario

## Notes

This is a new deterministic scenario, so it has no pre-change arm. Recording a
before/after score would manufacture a baseline rather than measure a skill
change. It therefore remains `NO_EVAL`; its acceptance evidence is the
fixture-to-independent-reference comparison and adversarial follow-up checks.

B3 introduces a five-row ad-spend source and a five-row conversion source. It
allows only casefolded/whitespace-normalized matches and a one-to-one
50-character truncation, preserves both unmatched identity lists, and requires
the matched-conversions-only CPA decision. The deliberately similar `Summr
Sale` row must stay unmatched; accepting it with fuzzy matching changes the
landed rows, match facts, and both side-specific rates.

No authenticated agent E2E is claimed. The normal intake gate owns operator
approval; B3 does not use an agent-authored approval field as graded evidence.

## Evidence

- `evals/dp-scenarios/tests/test_scenario_marketing_attribution.py` — fixture
  reproducibility, exact independent gold, safe-match acceptance, fuzzy-match
  rejection, CPA-policy mutation, and missing-evidence behavior.
- `evals/dp-scenarios/tests/test_scenario_loader.py` — `full` tier selection,
  package inventory, and run-order isolation.
- `evals/dp-scenarios/tests/test_followup_registry.py` — B3's explicit
  reproducibility and loader-cross-check intent.

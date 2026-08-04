---
id: 2026-08-04-skill-language-aligned-with-public-docs
date: 2026-08-04
label: "user-facing skill language aligned with the public docs; eight review findings fixed"
plugin_version: 0.35.3
status: NO_EVAL
scenarios: []
record: null
---
# Benchmark — user-facing skill language aligned with the public docs; eight review findings fixed

## Notes

No eval arm can distinguish this change, and the attempt to build one is the most
useful thing this entry records.

The bulk of the diff is terminology: `data product` in prose where skills wrote
bare `DP` or title-case `Data Product`, `infra profile` where the hyphenated form
belongs only in flags and URLs, `Nextdata OS` as the product name. Compound
modifiers the docs themselves use (`cross-DP`, `per-DP`, `DP-to-DP`) and literal
CLI output (the `DP Activation ID` column, `list-dps`) are deliberately preserved.
No scenario checker greps for any of this — verified by reading the `checks.json`
of every affected scenario for references to the changed vocabulary; the single
hit (`policy-compliance-failure` / `gives-exact-verify-commands`) names a CLI
command this PR does not touch and passed in both arms.

**A paired run was attempted anyway, and produced a false signal worth recording.**
19 affected scenarios (`affected_scenarios.py`) were run on `cdc0466` and on this
branch, agent `gpt-5.6-luna`, judge `gpt-5.6-terra`, uncached on both sides. The
comparison showed three scenarios losing one to two checks. Each was investigated:

- `pgvector-embedding-type-failure` (5/5 → 4/5) and `policy-compliance-failure`
  (5/5 → 4/5). Both failing checks concern the agent's *evidence trail* — "no
  describe/status-reason or logs content is actually shown as read", "does not
  show the agent identifying the required namespace". The diff to
  `nxd-debug-data-product` is three `DP` → `data product` substitutions with
  "Read init logs" and the `Evidence:` list byte-identical, so no instruction to
  read logs was weakened. Re-running both on unchanged `cdc0466` returned
  PASS/PASS with different tool counts (7 vs 6, 10 vs 12).
- `add-scenario-to-suite` (12/12 → 11/12), on the check
  `cites-lower-bound-not-mean`. This one had a plausible mechanism: the FAIL
  verdict text in `nxd-run-evals` was rewritten in this PR, and the judge said the
  agent grounded its verdict in "insufficient ±5% precision" — REFUSE reasoning —
  rather than the lower bound. The verdict block was restructured to separate the
  three verdicts. The score then went to 10/12: *worse*. That is the point at
  which the hypothesis should be abandoned rather than iterated on.

Three runs of `add-scenario-to-suite` on **unchanged** `cdc0466`:

```
12/12 PASS   10/12 FAIL   12/12 PASS
```

Baseline spans 10–12 on identical code. Both measured values on this branch (11,
then 10) fall inside that range. At N=1 per arm this suite cannot separate a
one-check regression from run-to-run variance — which `evals/skill-sets.yaml`
already says in its `no_review_control` comment ("agent variance across identical
prompts is large enough that a single [run is insufficient]"), and which this
exercise confirms with numbers.

The verdict restructuring was kept, but on its own merits rather than as a fix:
the previous FAIL definition read *"mean clears target but lower bound doesn't"*,
which describes only one of the two ways a run fails and silently omits the case
where the mean misses outright. Two directives added purely to chase the phantom
regression — instructing the agent how to phrase its verdict — were removed again,
because prompt-shaping aimed at one eval check is not guidance.

**One real defect was caught by the run, and it was introduced by this PR.** The
static-artifact gloss `null · the manifest didn’t say` uses a typographic
apostrophe (U+2019) inside a string `nxd-render-static-artifact` instructs the
agent to grep the rendered HTML for verbatim, so a straight-quote render fails the
skill's own validation and is reported as "the render dropped a declared value" —
a wrong diagnosis for an encoding mismatch. `reference/contract.md` already
disagreed with itself about the apostrophe (ASCII at :121, U+2019 at :126), so the
hazard had bitten before. The replacement `null · not declared` is apostrophe-free
by construction. The first sweep changed `src/` but not the eval fixtures that
assert the same literal, which crashed `dp-static-artifact-lifecycle` outright
(`AssertionError`); fixing the three fixture sites took it from 3/6 to 5/6.

The remaining changes are adversarial-review findings verified individually
against the source before being applied. Roughly half the raised findings were
rejected as wrong on inspection — notably a claim that the mandatory self-check
command is broken, which reads the `python3 self_check.py` line without the
`cp "$JOB_HELPER_DIR/scripts/self_check.py"` immediately preceding it.

**One accepted finding was wrong and has been reverted.** An earlier revision of
this PR "corrected" the DP REST auth header from `x-nextdata-token` to
`Authorization: Bearer`, on the evidence that
`nxd-query-data-product/scripts/nxd_api.py:353` sends Bearer. That is one
client's implementation, not the server contract, and generalising from it was
the error. Checkable from inside this repo: the vendored public examples send
`x-nextdata-token` against DP endpoints — see
`src/nxd-build-data-product/reference/nextdata-public-examples/data_products/competitor_growth_analysis/assets/rag_chatbot.py:67`
and `.../example_mcp/notebooks/03-mcp-tutorial.ipynb:154`. The platform docs
agree (in the `nxd` repo, `components/docs`:
`how-to/infra-profiles/provisioning.md`, `dp_development/model-orchestration.md`,
`dp_development/mcp_tools.md`, `operations/automation_identity.md`), where
`Authorization: Bearer` appears only for SCIM. The original text also hedged "or `Authorization: Bearer` on
multi-domain environments" — a distinction that does not apply under
single-domain, which is the deployment in question. All four edits
(`nxd-query-data-product/SKILL.md` ×2, its `reference/troubleshooting.md`, and
two sibling files in `nxd-build-data-product`) are reverted to the original
wording. The lesson is narrow and worth keeping: a shipped client's header is
evidence about that client, not about the API.

## Evidence

- `python3 scripts/validate_skills.py --root .` — passes.
- `python3 -m pytest evals/tests` — 610 passed (610 on `origin/main`; this PR adds
  no test and changes two existing fixtures to the new gloss literal).
- `evals/tests/test_static_artifact_lifecycle_gate.py` — the carrying test. Its
  gloss tuple asserts the exact literal the skill greps for; it fails against this
  PR's `src/` change if the fixtures are left on the old string, which is precisely
  the breakage the first sweep caused and this PR fixes.
- `evals/public/dp-static-artifact-lifecycle/fixtures/check_static_artifact.py` —
  the scenario-side assertion of the same literal, at :307 and :343.
- `./build-skills.sh` — packages all 17 skills, each under the 200-entry cap.
- `python3 evals/benchmark_record.py --check` — passes.
- Version lockstep: `plugin.json`, `marketplace.json` and all 17 `SKILL.md`
  `metadata.version` at 0.35.3.

---
id: 2026-09-16-contract-binding-and-flat-layout-guards
date: 2026-09-16
label: "Contract param binding, verify substance, flat-layout packaging and unrequested-surface guards in nxd-build-data-product, measured against a regeneration"
plugin_version: 0.51.1
status: NO_EVAL
scenarios: []
record: null
---
# Benchmark — contract binding, verify substance, flat-layout packaging and unrequested-surface guards

## Notes

No eval arm exists and none can be built honestly. Every fault addressed here is
invisible to both gates a scenario could grade. `nxd validate` imports the bundle
and resolves infra-profile services; it never executes a transform and never
executes a contract, so a wrongly-bound verify parameter and an unconditional-PASS
contract body both validate clean. The flat-layout packaging fault surfaces only
under `nxd launch`, which no public scenario runs because it deploys to a live
mesh. A scenario manufactured to grade these would be grading its own fixture.

The evidence is instead an observed generation. A data product was generated from
`example-input/store-sales-data-product.md` into `example-output/store-sales/` by
an agent holding this skill and nothing else, and reviewed against the product it
was modelled on (`store-sales` in the ecommerce-demo showcase). It converged on
the spec surface — name, domain, profile, environment, version, input and port
names, both promise names, the expectation name, all three controls, the ten-attribute
model and all nine glossary links matched. Four faults survived `nxd validate`
exiting 0.

**1. Contract parameters bound by name, guessed wrong, in all three contracts.**
Each carries `def verify(input: AzureDataLakeStorage, models: dict[str, Model])`.
Arguments bind by name (`nxd/data_product/mark.py`: named arguments are the
default and "the argument name must follow a specific naming pattern
convention"), so a contract wired with `.service(service_name="adls", ...)` binds
to `adls`. `input` matches no declared service or port. The skill stated this rule
for `transform(...)` at `SKILL.md:369` and nowhere for contracts;
`promises-contracts.md` demonstrated the correct form only by example, naming a
Snowflake context `snowflake`, which an author reads as a type hint rather than a
binding. The rule is now stated for contracts in both places, with the reason it
escapes validation.

**2. Nothing required a verify body to be capable of failing.** This generation's
contracts happened to be substantive — they read the published CSV and return
`FAILED` with offending values and row counts. The product they were modelled on
does the opposite: all three of its contracts return `PASS` unconditionally. So
the pack's own bundled examples teach the anti-pattern, and the skill had no line
contradicting them. `promises-contracts.md` now says a verify that cannot fail is
a defect, shows the wrong and right shapes, and warns that example fixtures ship
the wrong one.

**3. The flat-layout packaging guard was documented but not enforceable.** The
generated bundle ships five top-level modules (`spec`, `models`, `nxd_spec`,
`nxd_models`, `transform`; `local_test.py` is excluded by `.nxdignore`) with
neither an `__init__.py` at the root nor a `[tool.setuptools] py-modules` block:

```
ls example-output/store-sales/*.py | grep -v local_test   # 5
ls example-output/store-sales/__init__.py                 # No such file
grep -c py-modules example-output/store-sales/pyproject.toml   # 0
```

`SKILL.md` and `best_practices.md` both described the hazard, so this was
non-compliance rather than ignorance — but the preflight bullet that should have
caught it read "`pyproject.toml` ships every module/package needed by `spec.py`",
which scans as a dependency question. It is now a binary check: count shipped
top-level modules, require one of the two guards, with the exact
`Multiple top-level modules discovered in a flat-layout` failure string and a note
that validation passing is not evidence.

**4. Unrequested surface was added to look thorough.** `.managed_access()` on the
output port (`spec.py:94`) and an invented executor `.config(k8s_executor_config)`
on the transform (`spec.py:57`) appear in neither the input document nor the
product being modelled. Both change deployed behaviour: the first alters access
semantics, the second pins memory and CPU. The preflight checked for hidden demo
values and import integrity but had no bullet for surface the user never asked
for. It does now, naming the access-control and approval modifiers specifically.

A fifth change is not a generation fault but a pitfall both this generation and a
second one hit from opposite sides. `promotion_id` is empty on roughly three
quarters of the 23,381-row extract. A default `pd.read_csv` turns those blanks
into `NaN` and writes them back as the literal text `nan`; reading with
`dtype=str, keep_default_na=False` keeps them empty. The reviewed generation got
this right unprompted. A separate generation of the same document got it wrong,
reproducibly:

```
POS-000002,154000004602,15,1904.7,USD,2025-08-17T19:36:28Z,STORE-076,EU,kiosk,nan
```

The skill had no coverage of it at all, in a pack whose common case is
lift-and-shift of exactly this shape. It is now in `common-pitfalls.md` under
Transform issues, with the instruction to check it against a real extract rather
than a hand-written sample, since samples rarely carry the empty fields that
trigger it.

**The rules are executable, not just documented.** Fault 3 was already described
in prose in two places and shipped anyway, which is the argument against fixing
any of this with more prose. So the skill now ships
`scripts/preflight_check.py`: standard-library only, never imports the product
under test, and decides all four faults statically before dependencies are
installed. Run against the three products to hand, it reports exactly the faults a
reader found and nothing else — 4 errors and 1 warning on the reviewed
generation, 3 errors on a second generation whose contracts were TODO stubs, and
2 errors on the ecommerce-demo product they were both modelled on, whose contracts
return unconditional `PASS`. That last result is the point: the pack's own
reference example fails the check, which is why an agent reading it produced the
same shape.

**Measured, on a regeneration from the unchanged input document.** The same agent
rebuilt the product with the updated skill, and the split is the whole argument
for making rules executable. All four checker-enforced faults closed: contracts
now bind `adls`, all three reference `FAILED`, `py-modules` lists the five shipped
modules, and the two versions agree. The fifth rule, unrequested surface, was
prose only, and `.managed_access()` and the invented executor `.config(...)`
survived untouched with no rationale written for either. Four out of four when
mechanically checked; zero out of one when described. So `surface` is now a check
too — WARN rather than ERROR, since intent is not mechanically knowable, asking
for the rationale to exist in writing rather than forbidding the modifier.

**A latent contradiction in the source demo surfaced, which is the rule working.**
Forced to write a `FRESHNESS_PROMISE` body that could actually fail, the agent
measured the published lag at 123.7 minutes against a 5-minute budget and
reported the conflict. That promise is unholdable for an eight-hourly batch
product: the ecommerce-demo original carried the identical 5-minute claim and hid
it behind an unconditional `PASS`. The agent's own fix, anchoring the newest
transaction to the current instant, brought the lag to 0.0 min but rotated every
row's time of day by 2h25m on a product whose stated purpose is hour-sensitive
in-store analysis, and made the promise true only at the moment the platform
happens to evaluate it. The input document now carries a 24-hour budget matched
to the cadence and a whole-day rebase requirement, so the promise is true by
construction while healthy and false once the pipeline stops for a day. The
correction is in the document, not the skill: the budget is a fact about this
product.

**`nxd validate` does not check driver strings, at all.** Verified while
confirming an open item the regeneration raised: a wrong driver version
(`nxd:kubernetes/contract:9.9.9`) and a fabricated driver name
(`nxd:totally-made-up:1.0.0`) both exit 0, while a bogus *service* name fails
immediately. That asymmetry is what makes the silence read as approval. Recorded
in `common-pitfalls.md` and the preflight checklist as a by-eye item, deliberately
not automated: the contract driver does not appear as a service in the profile, so
a naive cross-check would false-positive on the correct answer.

**Second regeneration: the `surface` rule held, and a worse bug surfaced under it.**
Made executable, `surface` worked on the first try: `.managed_access()` and the
executor config are both gone, and the checklist records their absence as a
decision, citing the check that caught them. The generation also disputed a line
in the input document and was right to. `.service(service_name=..., driver=...)`
selects the *context class* handed to the contract, and the document named the
contract-executor driver. Measured against the installed package,
`storage_context_type_for_driver("nxd:kubernetes/contract:1.0.0")` returns a bare
`Context`, byte-identical to what a fabricated driver returns, while
`nxd:adls:2.0.0` returns `AzureDataLakeStorage`. The package excludes the executor
driver from service resolution in three places, commented "it is not an
infra-profile service" (`_spec.py:1647,2021,3737`), and sets the contract executor
itself (`:1035-1039`). So every `adls.container` and `adls.model_paths` in a
contract wired that way raises at verification time.

That bug was in the ecommerce-demo original, in this skill's own worked example
added earlier in this same change set, and in a second generation, and none of
them failed: a contract that returns `PASS` without touching its context never
dereferences anything. The unconditional-`PASS` fault was hiding the wrong-driver
fault. Fixing the first is what exposed the second, which is the argument for the
first rule restated as consequence. Now `contract-driver`, an ERROR-level check,
plus the corrected example and the rule in `promises-contracts.md`.

**One reported failure was not one.** The same generation again chose to anchor
the extract to the current instant, against an input document that now forbids it
in terms. The document was edited at 16:24 and the build written from 16:32, so
the text was on disk, but the generation's own README quotes the *old* sentence
("available within 5 minutes of the transaction"), which the current document no
longer contains. It rebuilt from a copy held in context rather than re-reading the
file. Recorded in `SKILL.md` as a rule, since iterating on an input document
between runs is the normal shape of this work and a stale read looks exactly like
defiance.

**A "cannot be verified" claim that was simply false.** Four consecutive
generations shipped a glossary link to `#/terms/region`, each one dutifully
recording the nine term IDs as unverifiable open decisions, because the input
document told them no endpoint lists glossary term IDs. The gateway's `glossary`
tool returns the term dictionary keyed by exactly those IDs. The glossary holds
63 terms and `region` is not among them; the intended term is `sales_region`, and
the link has resolved to nothing since the product was written. Checked against
the live glossary, it is the only invalid `#/terms/` reference anywhere in the
ecommerce showcase.

The failure mode is what makes this worth a rule rather than a correction: a
wrong term ID is stored verbatim and resolves to nothing, so the attribute
carries no glossary meaning while appearing to, and `nxd validate`, launch and
the deployed read-back all stay silent. The skill now requires every term ID to
be verified against the fetched glossary, including IDs an input document
supplied, and says never to record them as unverifiable. `common-pitfalls.md`
carries the fetch command, the worked example, and the related fact that the host
in a glossary URL is parsed away entirely, so a broken link is never diagnosed by
looking at it.

## Evidence

- `evals/tests/test_dp_preflight_check.py` — 23 tests pinning the checker against
  a fixture pair (`evals/tests/fixtures/dp_preflight/{guarded,unguarded}`): the
  guarded product is clean, the unguarded one trips all four checks, either
  packaging guard is accepted, an incomplete `py-modules` list is caught,
  `.nxdignore`d modules do not count as shipped, hyphens normalise to underscores
  in parameter binding, `verify-weak` is reported independently of `verify-bind`,
  the exit code is driven by errors rather than warnings, and `surface` flags an
  unjustified access modifier, accepts one the README explains, tells a storage
  config (a call) from an executor config (a bare name), and never fails the run. Verified to fail
  against the previous implementation: with `scripts/preflight_check.py` removed,
  collection fails outright (`FileNotFoundError`), and `test_checker_ships_with_the_skill`
  exists to name that as the failure rather than leave it an import accident.
- `src/nxd-build-data-product/scripts/preflight_check.py` — the checker, wired
  into `SKILL.md` "Generated-Code Preflight" and the reference checklist's
  Required review.
- `example-output/store-sales/contracts/*.py` — three verify functions, each
  declaring `input: AzureDataLakeStorage` as its service-context parameter, the
  fault guard 1 addresses. `nxd validate example-output/store-sales` exits 0 with
  all three present.
- `example-output/store-sales/{pyproject.toml,__init__.py}` — the three commands
  above reproduce the missing packaging guard; five top-level modules ship.
- `example-output/store-sales/spec.py:56,95` — the executor config and
  `.managed_access()` that survived the regeneration, now reported as two
  `surface` warnings by the checker and justified by no README line.
- Driver-string blind spot reproduced by editing a working `spec.py`: bogus
  version exit 0, fabricated driver name exit 0, original restored exit 0.
- `storage_context_type_for_driver` measured directly: `nxd:adls:2.0.0` ->
  `AzureDataLakeStorage`, `nxd:s3:1.0.0` -> `(S3Input, S3Output)`,
  `nxd:kubernetes/contract:1.0.0` -> bare `Context`, `nxd:totally-made-up:1.0.0`
  -> bare `Context`. The `contract-driver` check reports 2 errors each on the
  ecommerce-demo original and on the earlier generation, and none on the current
  one.
- `example-input/store-sales-data-product.md` — the input document the generation
  worked from, unchanged by this PR, so a re-run measures the skill rather than a
  reworded prompt.
- `python3 scripts/validate_skills.py --root .` — passes.
- `./build-skills.sh` — passes, including the 200-entry per-skill cap and plugin
  archive validation, at 0.51.1.
- Version lockstep: `.claude-plugin/plugin.json` 0.51.0 → 0.51.1, three
  `marketplace.json` occurrences, and all 18 `src/*/SKILL.md` `metadata.version`
  values bumped together. Rebased onto `origin/main` at 2182cea, which had taken
  0.51.0 in the meantime. Patch rather than minor: no skill is added and no new
  capability ships, the guidance of an existing skill is tightened.
- Glossary verification measured against the live mesh: 63 terms fetched,
  `region` absent, `sales_region` present, 8 of the 9 asserted IDs valid; the
  deployed `store-sales-demo` reads back `region_id -> termId=region`. Fixed
  upstream in nextdata-tech/ecommerce-demo#278.
- Files changed: `src/nxd-build-data-product/SKILL.md`,
  `reference/promises-contracts.md`, `reference/common-pitfalls.md`,
  `reference/generated-code-preflight.md`.

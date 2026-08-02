# The spec is authoritative — architecture

How a Nexty Pocket data product goes from user intent to a running, queryable
closure, and how the pipeline records what it did. This note is normative: it
specifies shapes, names and literals, because several independent producers must
agree on them exactly.

## Contents

- [0. The model](#0-the-model)
- [1. The unified diagnostic record](#1-the-unified-diagnostic-record)
  - [1.8.2 `inspect_run` — the measured contract](#182-inspect_run--the-measured-contract)
- [2. The build record](#2-the-build-record)
- [3. The lock file and the canonical hash](#3-the-lock-file-and-the-canonical-hash)
- [4. The closure layout](#4-the-closure-layout)
- [5. The materialization predicate](#5-the-materialization-predicate)
- [6. The stage ladder and the failure taxonomy](#6-the-stage-ladder-and-the-failure-taxonomy)
- [7. The middleman presentation rules](#7-the-middleman-presentation-rules)
- [8. Elicitation and UI prerequisites](#8-elicitation-and-ui-prerequisites)
- [9. Frozen strings — the cross-file contract](#9-frozen-strings--the-cross-file-contract)
- [10. Design boundaries](#10-design-boundaries)

---

## 0. The model

**User intent is the source, `dp-spec.md` is the IR, `nxd-generate-dp` is codegen,
the closure's Python is the output artifact.** Everything below follows from
that framing, and two consequences are load-bearing throughout:

1. **An IR is a pure function of its source, so outcomes cannot live in it.**
   The plan and what happened to it are different files, produced by different
   actors.
2. **A compiler does not edit your source to make the build pass.** The self-heal
   loop may change generated code; it may **never** change the IR. Reaching green
   by narrowing the population, dropping a model whose grain won't resolve, or
   relaxing a threshold is a **spec edit requiring re-approval**, not a heal.
   §2.5 makes this mechanically checkable.

Concretely: the live, hand-edited `dp-spec.md` sits **beside** the closure. At
generation time the approved spec is **byte-copied into** the closure as
`dp-spec.approved.md` next to a `dp-spec.lock.json` carrying its canonical hash
and the compiler version. Build outcomes live in a generated `build-record.json`.
Self-containment is a hash-checkable snapshot, not a prose discipline. Every
producer in the pipeline — `validate_dp_spec.py`, `self_check.py`, the build
loop — emits the **same** diagnostic shape, differing only in which stage
produced it.

---

## 1. The unified diagnostic record

One shape, emitted by every stage. This is the most important section: three
independent producers must agree on it byte-for-byte.

### 1.1 The record

```jsonc
{
  "schema":   "nxd-diagnostic-v1",
  "stage":    "s0_spec",              // closed vocabulary, §1.2
  "code":     "spec.criteria.incomplete_scale",   // closed registry, §1.5
  "severity": "error",                // error | warning | info
  "owner":    "agent",                // agent | user | environment
  "origin":   "tool_computed",        // agent_observed | supervisor_reported
                                      // | tool_computed | llm_authored | unbound
  "path":     "spec:criteria[C1].anchors",        // grammar in §1.6
  "message":  "scale 1-5 has no anchor for level(s) [2, 3, 4]",
  "evidence": { "expected": [1,2,3,4,5], "found": [1,5] },
  "fix":      "Author anchors for 2, 3 and 4, or carry the gap as an open question."
}
```

`schema`, `stage`, `code`, `severity`, `owner`, `origin`, `path`, `message` are
**required**. `evidence` defaults to `{}`. `fix` is optional (`null` or absent).
No other keys are permitted — an unknown key is a producer bug, and the shared
validator rejects it.

`origin` exists because classification fails closed (§6.4). An agent-inferred
field is visibly weaker evidence than a supervisor-reported one, and the
classifier must be able to see the difference without parsing prose. `unbound`
means *the schema defines this field and no producer exists yet* — that is how
stage-4 detail is carried until a supervisor binds it.

### 1.2 `stage` — closed vocabulary

Nine values, ordered. The `s<N>_` prefix makes the ordinal recoverable by
`int(stage[1])` and makes lexicographic sort equal pipeline order.

| `stage` | What runs | Offline? | Notes |
|---|---|---|---|
| `s0_spec` | `validate_dp_spec.py` — the IR alone | yes | blocker or agent-fillable gap |
| `s1_structure` | `self_check.py` Phase A — ast vs pinned DSL, nothing executed | yes | malformed code, self-heal |
| `s2_transform` | `self_check.py` Phase B — transform executes for real, scratch DuckDB, no kernel, no network | yes | **user-code runtime error, unambiguously the code** |
| `s3_closure` | `self_check.py` Phases C + D | yes | structural / governance, self-heal |
| `s4_pin` | supervisor pins & compiles the closure to YAML (`build_data_product`) | no | **code fault Phase A cannot see** |
| `s5_serve` | provision / serve (kernel, deps, endpoint) | no | usually environment |
| `s6_run` | transform on the supervisor | no | mixed |
| `s7_publish` | publish / verify / artifact | no | mixed |
| `s8_answer` | describe / query | no | green build, wrong answer |

`OFFLINE_STAGES = {"s0_spec", "s1_structure", "s2_transform", "s3_closure"}`.
**A failure at an offline stage is never environmental.** This is not a heuristic;
those stages touch no kernel, no network and no supervisor.

Phases C and D share `s3_closure`; `code` and `path` distinguish them. Splitting
them would buy nothing — both are offline, both are agent-owned, both self-heal.

### 1.3 `severity`

| value | meaning |
|---|---|
| `error` | gates. The stage's status is `failed`. |
| `warning` | does not gate, but must reach the build record and must be considered before claiming anything. |
| `info` | data, not judgement. Row counts, distribution read-back rows, attempt bookkeeping, the Phase A `unverified:` blind-spot list. |

Severity does **not** decide who hears about it. `owner` does (§7).

### 1.4 `owner` — and the presentation consequence

| value | meaning | who fixes it |
|---|---|---|
| `agent` | structural, or user-code runtime | the agent, by self-healing generated code |
| `user` | a ruling, a credential, an answer only the user has | the user |
| `environment` | neither can fix it by editing anything | retry |

The presentation rule that hangs off this field (full form in §7):

- `owner == "user"` → the user hears it, phrased as a **blocker**.
- `owner == "agent"` **and** `code` begins `concession.` → the user hears it,
  phrased as a **concession**.
- everything else → the agent absorbs it.
- `owner == "environment"` once `caps.retry_environmental_total` is exhausted
  (§2.10) → **re-emitted** with `owner: "user"` and
  `code: "blocker.caps_exhausted"`. An unfixable environment is a thing the user
  must hear about; a retryable one is not.

The re-emission trigger names a **specific counter**, deliberately. "After caps
are exhausted" would be undefined for an environmental failure: the remap and
regenerate caps are not consumed by a retry (§6.7), so without a retry bound of
its own an environmental failure could retry forever and never reach the user.
§2.10 carries that bound.

When the remedy is "supply a credential", the diagnostic is `owner: "user"`
(`env.credential_missing`), not `environment` — the user must act, so the user
hears it.

### 1.5 `code` — grammar and registry

Grammar: `<domain> "." <slug> [ "." <slug> ]`, lowercase, `[a-z0-9_]` segments.
Stable forever: a code is never renamed or repurposed; a changed meaning is a new
code. Unknown codes fail the shared validator.

The registry is **`<nxd-pocket-loop>/scripts/dp_diagnostics.py::CODES`**, a mapping
`code -> {stage, severity, owner, control, agent_fillable, summary}`. Producers
supply `code` plus per-instance `path`/`message`/`evidence`.

**`severity` is registry-default and producer-overridable, downward only** — a
producer may relax `error` to `warning`, never the reverse.

**`owner` is NEVER producer-overridable.** It comes from the registry and only
from the registry. A diagnostic whose ownership changes is **re-emitted under a
new code**, never mutated in place — which is how the design handles the one
legitimate ownership transition (`environment` → `user` becomes
`blocker.caps_exhausted`, §1.4), and follows directly from "a changed meaning is
a new code" above.

The asymmetry is deliberate, and it is not stylistic. `owner` is the field that
decides whether the human hears about a diagnostic at all (§7) and how a failure
counts against materialization (§5.1). A producer-relaxed `severity` costs a
warning; a producer-demoted `owner` silences a blocker. `dp_diagnostics.py`
rejects any report whose diagnostic carries an `owner` differing from its
registry entry, and `test_dp_diagnostics_schema.py` pins that rejection.

`control` serves the elicitation UI (§8): it tells a harness which form control
to render for a spec-addressed error. Values: `text`, `long_text`, `number`,
`enum`, `list`, `mapping`, `table`, `confirm`, `none`.

#### Domain `spec.` — stage `s0_spec`, produced by `validate_dp_spec.py`

Every check in `validate_dp_spec.py` maps to exactly one code, and the mapping is
complete in both directions. **Completeness is enforced, not asserted** (§1.5.1):
the table is documentation, and `test_validator_code_coverage.py` is the
contract.

| code | sev | owner | control | agent-fillable |
|---|---|---|---|---|
| `spec.encoding.not_utf8` | error | agent | none | no |
| `spec.frontmatter.unparseable` | error | agent | none | yes |
| `spec.frontmatter.missing_key` | error | agent | text | yes |
| `spec.frontmatter.bad_version` | error | agent | number | yes |
| `spec.frontmatter.bad_name` | error | agent | text | yes |
| `spec.frontmatter.bad_status` | error | user | enum | no |
| `spec.frontmatter.approved_with_errors` | error | user | confirm | no |
| `spec.frontmatter.rubric_version_missing` | error | user | text | no |
| `spec.section.missing` | error | agent | none | yes |
| `spec.section.empty` | error | agent | none | yes |
| `spec.section.unknown` | warning | agent | none | no |
| `spec.section.unparseable` | error | agent | long_text | no |
| `spec.source.no_entries` | error | agent | table | yes |
| `spec.source.not_mapping` | error | agent | mapping | yes |
| `spec.source.bad_type` | error | agent | enum | yes |
| `spec.source.no_location` | error | user | text | no |
| `spec.source.no_scope` | error | user | long_text | no |
| `spec.source.credential_value` | error | user | none | no |
| `spec.source.credential_key_mapping` | error | user | none | no |
| `spec.source.label_missing` | error | agent | text | yes |
| `spec.source.label_duplicate` | error | agent | text | yes |
| `spec.population.not_mapping` | error | agent | mapping | yes |
| `spec.population.prose` | warning | agent | mapping | yes |
| `spec.population.missing` | error | user | long_text | no |
| `spec.model.no_entries` | error | agent | table | yes |
| `spec.model.no_name` | error | agent | text | yes |
| `spec.model.bad_name` | error | agent | text | yes |
| `spec.model.bad_kind` | error | agent | enum | yes |
| `spec.model.no_description` | error | agent | long_text | yes |
| `spec.model.no_grain` | error | user | long_text | no |
| `spec.model.no_key` | error | user | list | no |
| `spec.model.duplicate_name` | error | agent | text | yes |
| `spec.model.unmotivated` | warning | agent | list | yes |
| `spec.gate.not_mapping` | error | agent | mapping | yes |
| `spec.gate.no_rule` | error | user | long_text | no |
| `spec.gate.no_unknown` | error | user | enum | no |
| `spec.gate.unknown_is_fail` | error | user | enum | no |
| `spec.criteria.no_entries` | error | agent | table | yes |
| `spec.criteria.no_weight` | error | user | number | no |
| `spec.criteria.bad_weight` | error | user | number | no |
| `spec.criteria.weights_unbalanced` | error | user | table | no |
| `spec.criteria.no_scale` | error | user | mapping | no |
| `spec.criteria.bad_scale` | error | user | mapping | no |
| `spec.criteria.no_anchors` | error | agent | mapping | yes |
| `spec.criteria.incomplete_scale` | error | agent | mapping | yes |
| `spec.criteria.anchor_out_of_range` | error | agent | mapping | yes |
| `spec.criteria.bad_provenance` | error | agent | enum | yes |
| `spec.verdict.missing` | error | agent | table | yes |
| `spec.verdict.not_mapping` | error | agent | mapping | yes |
| `spec.verdict.no_values` | error | user | list | no |
| `spec.verdict.band_no_verdict` | error | agent | text | yes |
| `spec.verdict.band_unknown_verdict` | error | agent | enum | yes |
| `spec.verdict.band_unreachable` | error | user | mapping | no |
| `spec.verdict.value_unreached` | error | user | table | no |
| `spec.verdict.no_precedence` | error | user | long_text | no |
| `spec.judgment.no_entries` | error | agent | table | yes |
| `spec.judgment.no_model` | error | agent | text | yes |
| `spec.judgment.bad_produced_by` | error | agent | enum | yes |
| `spec.judgment.no_generator_model` | error | agent | text | yes |
| `spec.judgment.no_rubric_version` | error | agent | text | yes |
| `spec.judgment.bad_reruns` | error | agent | enum | yes |
| `spec.judgment.evidence_disabled` | error | user | confirm | no |
| `spec.schedule.not_mapping` | error | agent | mapping | yes |
| `spec.schedule.bad_trigger` | error | agent | enum | yes |
| `spec.schedule.no_cron` | error | user | text | no |
| `spec.schedule.no_cursor_field` | error | user | text | no |
| `spec.schedule.regrain_not_append_safe` | warning | user | confirm | no |
| `spec.output.not_mapping` | error | agent | mapping | yes |
| `spec.output.no_name` | error | agent | text | yes |
| `spec.output.unknown_model` | error | agent | enum | yes |
| `spec.output.bad_kind` | error | agent | enum | yes |
| `spec.decision.no_id` | error | agent | text | yes |
| `spec.decision.bad_status` | error | agent | enum | yes |
| `spec.decision.bad_provenance` | error | agent | enum | yes |
| `spec.decision.no_ruling` | error | user | long_text | no |
| `spec.decision.blocked_with_applies_to` | error | agent | none | yes |
| `spec.decision.no_applies_to` | error | agent | list | yes |
| `spec.decision.duplicate_id` | error | agent | text | yes |
| `spec.decision.missing_for_ruling` | error | agent | table | yes |
| `spec.decision.ruling_uncovered` | error | agent | table | yes |
| `spec.decision.sample_rule_unrecorded` | error | agent | table | yes |
| `spec.open_question.not_mapping` | error | agent | mapping | yes |
| `spec.open_question.no_question` | error | agent | long_text | yes |
| `spec.open_question.bad_disposition` | error | agent | enum | yes |
| `spec.open_question.answered_without_decision` | warning | agent | table | yes |
| `spec.question.unanswered` | warning | agent | list | yes |
| `spec.approval.agent_authored_at_approved` | warning | user | confirm | no |
| `spec.prefill.empty_required_field` | warning | agent | none | yes |

#### 1.5.1 Keeping the `spec.` registry complete — by construction

Three things make the completeness claim above true rather than merely stated.

**(i) The two many-to-one codes, enumerated.** Every other code has exactly one
call site. These two do not, and the discriminator is `evidence.reason` — a
closed enum, so no implementer invents another code for a variant:

| code | raised in | `evidence.reason` |
|---|---|---|
| `spec.frontmatter.unparseable` | the four `raise`s in `dp_diagnostics.split_frontmatter`, all surfaced at the one `except SpecReadError` in `validate_dp_spec.validate` | `missing` (no leading `---`) · `unterminated` (no closing `---`) · `unparseable` (delimited, but `yaml.safe_load` raised) · `not_mapping` (loaded, but not a YAML mapping) |
| `spec.criteria.bad_scale` | two call sites in `check_criteria` | `non_integer` (min/max not `int`) · `min_not_below_max` |

Both are fatal to further parsing at their own level:
`spec.frontmatter.unparseable` returns the report immediately, and
`spec.criteria.bad_scale` `continue`s past the anchor checks for that criterion.
Producers must not synthesize the downstream diagnostics that were never reached
— a not-reached check emits nothing, exactly as at the stage level (§2.2).

**The splitters have exactly ONE definition, in `dp_diagnostics.py`.**
`validate_dp_spec.py` imports `split_frontmatter` and `split_sections`; it does
not keep a copy. A copy is exactly how these drift: a duplicated splitter that
loses its `yaml.YAMLError` guard turns `name: [unclosed` into a raw traceback —
no diagnostic, no `--json`, and the exit-code contract broken. A docstring saying
"these must stay byte-for-byte equivalent" is not an enforcement mechanism. The
`reason` enum therefore lives on `SpecReadError` (the shared exception) rather
than on a validator-local error class, and `test_validator_code_coverage.py`
asserts both that the validator defines neither function and that its names are
the canonicalizer's objects.

The same drift class is why `dp_diagnostics._READ_FAILURES` exists and is used by
every "could not read the spec" CLI handler: `yaml.YAMLError` is **not** a
subclass of `ValueError`, so a handler catching `(SpecReadError, OSError,
ValueError)` looks exhaustive and is not.

**(ii) The `spec.source.credential_key_mapping` owner is `user`, deliberately.**
Structurally the agent could repair it (drop the value, keep the key name), which
would argue for `owner: agent`. It is `owner: user` for the same reason
`spec.source.credential_value` is: the shape that triggers it is a mapping whose
*value* is a live secret sitting in a shareable file. Only the user can decide
whether that secret must now be rotated, and silently rewriting the file would
erase the evidence that it leaked. Fail closed, and let the user hear it (§7).

**(iii) `evals/tests/test_validator_code_coverage.py` makes this mechanical.**

- every `report.error(` / `report.warn(` call site in `<nxd-pocket-loop>/scripts/validate_dp_spec.py`
  passes a `code=` argument (AST walk over the `Call` nodes — a call site with no
  `code=` fails the test);
- every such literal is a key in `dp_diagnostics.CODES` whose registry `stage` is
  `s0_spec`;
- **and the converse**: every `spec.*` key in `CODES` is emitted by at least one
  call site, with **one declared exemption**: `spec.encoding.not_utf8` is raised
  at the file-read boundary and exits 2 before a `Report` exists, so it is
  emitted outside the `report.error` path. It is listed by name in the test as
  the sole exemption — never a pattern, never a prefix, so a second uncovered
  code cannot slip in behind it. This is the direction that catches a dropped
  check — a code in the registry that nothing produces means a check went missing
  on the way in.

Adding a check to `validate_dp_spec.py` therefore *requires* adding a code, and
deleting a check *requires* deleting its code. Neither can happen silently.

#### Domain `struct.` — stage `s1_structure` (Phase A)

`struct.import_not_public_dsl`, `struct.model_name_not_literal`,
`struct.model_no_description`, `struct.view_empty_schema`,
`struct.view_field_not_metric_field`, `struct.unknown_dtype`,
`struct.unknown_agg`, `struct.agg_expression_forbidden`,
`struct.metric_in_model`, `struct.metric_first_arg_not_agg`,
`struct.bad_kwarg`, `struct.join_to_model_kwarg`,
`struct.primary_key_takes_no_args`, `struct.metric_of_and_column`,
`struct.description_unreachable`, `struct.role_no_description`,
`struct.join_target_missing`, `struct.no_primary_key`,
`struct.semantic_tools_forbidden`, `struct.bad_infra_profile`,
`struct.bad_script_path`, `struct.missing_call`, `struct.port_not_duckdb`,
`struct.port_no_storage`, `struct.promise_of_view`,
`struct.malformed_service_ref`, `struct.naming_invariant_promised_vs_models`,
`struct.naming_invariant_promised_vs_physical`,
`struct.base_models_vs_data_dirs`.

All `severity: error`, `owner: agent`, `control: none` — except
`struct.unverified` (`severity: info`), which carries Phase A's own declared
blind spot, one diagnostic per `unverified:` line.

#### Domain `runtime.` — stages `s2_transform`, `s6_run`

`runtime.import_failed`, `runtime.transform_raised`, `runtime.assert_failed`,
`runtime.base_models_mismatch`, `runtime.transform_incomplete`,
`runtime.model_table_missing` — all `error` / `agent`.
`runtime.row_count` — `info` / `agent`, one per model, `evidence: {model, rows}`.
At `s6_run`: `runtime.remote_assert_failed`, `runtime.remote_traceback`
(`error` / `agent`).

#### Domain `closure.` and `policy.` — stage `s3_closure` (Phases C, D)

| code | sev | owner |
|---|---|---|
| `closure.spec_snapshot_missing` | error | agent |
| `closure.lock_missing` | error | agent |
| `closure.lock_unparseable` | error | agent |
| `closure.lock_snapshot_byte_mismatch` | error | agent |
| `closure.lock_status_not_approved` | error | user |
| `closure.build_record_missing` | error | agent |
| `closure.build_record_invalid` | error | agent |
| `closure.build_record_hash_mismatch` | error | agent |
| `closure.readme_missing` | error | agent |
| `closure.resolved_ref_missing` | error | agent |
| `closure.escaping_reference` | error | agent |
| `closure.gitignore_missing` | error | agent |
| `closure.sensitive_missing` | error | agent |
| `closure.gitignore_not_naming_profile` | error | agent |
| `closure.canonical_hash_deferred` | info | agent |
| `policy.decisions_not_base_model` | error | agent |
| `policy.decisions_csv_missing` | error | agent |
| `policy.decisions_column_missing` | error | agent |
| `policy.decisions_value_out_of_vocab` | error | agent |
| `policy.literal_duplicates_landed_value` | error | agent |

#### Domain `semantic.` — the stage-8 tells

| code | stage | sev | owner |
|---|---|---|---|
| `semantic.distribution` | `s2_transform` | info | agent |
| `semantic.uniform_column` | `s2_transform` | warning | agent |
| `semantic.absent_vocabulary` | `s2_transform` | warning | agent |
| `semantic.query_error` | `s8_answer` | error | agent |
| `semantic.empty_result` | `s8_answer` | warning | agent |
| `semantic.truncated` | `s8_answer` | info | agent |
| `semantic.wrong_answer` | `s8_answer` | warning | agent |

The distribution read-back is emitted at **`s2_transform`**, because that is
mechanically where it runs — against Phase B's scratch DuckDB, before any build.
It is nonetheless the designated **stage-8 predictor**: a uniform classification
column is the tell that a green build will answer wrongly. It is non-gating, and
the build record **records and surfaces** it adjacent to concessions (§2.6).

#### Domain `pin.` — stage `s4_pin`

`pin.build_failed` (`error` / **`agent`** / `origin: agent_observed`),
`pin.spec_compile_error` (`error` / `agent` / `origin: supervisor_reported`; no
producer is wired, so it carries `origin: unbound` — see §1.8.2),
`pin.no_endpoint` (`error` / `agent`).

`pin.build_failed` is `owner: agent` **by construction**, not by evidence. This
is caveat 1 of §6.3 encoded in the registry.

#### Domain `env.` — stages `s5_serve`, `s6_run`, `s7_publish`

`env.supervisor_busy`, `env.provision_failed`, `env.dependency_install_failed`,
`env.kernel_unavailable`, `env.connection_refused`, `env.not_ready_timeout`,
`env.remote_unreachable` — all `error` / `environment`.
`env.credential_missing` — `error` / **`user`**.

#### Domain `publish.` — stage `s7_publish`

`publish.artifact_unavailable` (not retryable), `publish.release_unreadable`,
`publish.workflow_not_found`, `publish.superseded` (the `-32002` redirect;
`severity: warning`), `publish.trust_not_verified`, `publish.resource_not_found`.
Owner `environment` except `publish.trust_not_verified` (`agent`).

#### Domain `blocker.` — always `severity: error`, `owner: user`

The forbidden-invariant escalations and the user-input queue:

`blocker.forbidden_handwritten_yaml`, `blocker.forbidden_manual_watermark`,
`blocker.forbidden_replace_disposition`,
`blocker.forbidden_assert_restates_arithmetic`, `blocker.spec_edit_required`,
`blocker.open_question`, `blocker.caps_exhausted`, `blocker.credential_required`.

#### Domain `concession.` — always `severity: warning`, `owner: agent`

`concession.assert_weakened`, `concession.type_coerced`,
`concession.incidental_column_dropped`, `concession.sample_capped`,
`concession.dependency_repinned`, `concession.derived_model_left_inert`,
`concession.unverified_construct_accepted`,
`concession.readback_uniform_unexplained`, `concession.retry_reduced_scope`,
`concession.other`.

`concession.other` requires a non-empty `message` and `evidence.alternative`. It
exists so that "I did something the skills discourage and there is no code for
it" is still recordable. **Silence is never the fallback.**

#### Domains `heal.` and `meta.` — bookkeeping, always `severity: info`

`heal.attempt_started`, `heal.healed`, `heal.healed_with_concessions`,
`heal.caps_exhausted`, `heal.blocked`, `heal.retry_environmental`;
`meta.stage_not_reached`, `meta.classification_unsettled`.

### 1.6 `path` — grammar

```
path       := spec_path | closure_path | tool_path | ""
spec_path  := "spec:" segment ( "." segment )*
segment    := name [ "[" key "]" ]
key        := identity | "#" index
closure_path := "closure:" relpath [ ":" line ] [ ":" symbol ]
tool_path  := "tool:" toolname [ "." field ]
```

**Identity rule (mandatory — a UI keys controls on this).** The `key` is the
entry's own identity, resolved in this precedence: `id`, then `name`, then
`decision_id`, then `model`; only when none is present, `#<0-based index>`. Never
a bare index for an entry that has an identity — array indices move when a list
is edited, and a moving path is a UI that highlights the wrong field.

Examples:

```
spec:frontmatter.status
spec:criteria[C1].anchors
spec:models[scored_candidates].key
spec:sources[#0].location
spec:open_questions[fx_rates].disposition
spec:decisions[verdict_bands].applies_to
closure:models.py:scored_candidates.verdict
closure:transform/main.py:214
closure:data/scoring_rubric/scoring_rubric.csv:weight
tool:build_data_product.error
```

`path` is `""` only for a whole-run diagnostic with no address (e.g.
`meta.stage_not_reached`).

### 1.7 `evidence`

A JSON object, always present (`{}` when empty), always JSON-serializable, never
more than ~4 KB per diagnostic. Reserved keys with fixed meaning: `expected`,
`actual`, `found`, `allowed`, `count`, `rows`, `columns`, `traceback`,
`stdout_excerpt`, `exit_code`, `command`, `alternative`, `model`, `table`.

**Redaction is mandatory.** Every producer runs `evidence` and `message` through
the same `CREDENTIAL_VALUE_RE` that `validate_dp_spec.py` uses, replacing a match
with `<redacted>`. A check that prints the secret it found turns a contained file
leak into a transcript leak.

### 1.8 The report envelope

Any tool emitting diagnostics as its primary output uses:

```jsonc
{
  "schema": "nxd-diagnostic-report-v1",
  "tool":   "validate_dp_spec",       // validate_dp_spec | self_check | dp_diagnostics | loop
  "target": "…/dp-spec.md",
  "ok":     false,
  "counts": { "error": 3, "warning": 1, "info": 12 },
  "spec_hash": "sha256:…",            // when the tool knows it; null otherwise
  "diagnostics": [ /* nxd-diagnostic-v1 records */ ]
}
```

`tool` is a **closed enum of four values**, and `record append` validates the
field. Three name a script; the fourth names the agent:

| `tool` | who writes the report | stages it may carry |
|---|---|---|
| `validate_dp_spec` | `<nxd-pocket-loop>/scripts/validate_dp_spec.py --json` | `s0_spec` |
| `self_check` | `scripts/self_check.py --json` | `s1_structure`, `s2_transform`, `s3_closure` |
| `dp_diagnostics` | `<nxd-pocket-loop>/scripts/dp_diagnostics.py` (`lock verify`, `materialized`) | any |
| `loop` | **the agent**, hand-constructed from tool results | `s4_pin` … `s8_answer` |

`loop` exists because stages 4–8 have no script producer — the agent observes a
`build_data_product` error or a `list_data_products` row count and constructs the
report itself. Naming that honestly matters: a `loop` report is agent-constructed
and is **visibly weaker evidence** than a `tool_computed` report. Labelling it
`dp_diagnostics` would disguise an observation as a measurement, which is exactly
the fail-closed posture of §6.4 inverted. `record append --stage <s4…s8> --from
<report.json>` therefore expects `tool: "loop"` in the ordinary case and rejects a
report whose `tool` cannot produce the `--stage` it was given.

A `loop` report's diagnostics carry `origin: agent_observed` **unless the
relay criterion in §1.8.1 is met**.

#### 1.8.1 The relay criterion — when agent-written may claim `supervisor_reported`

`origin` records **who authored the claim, not who wrote the file.** Agent
transcription launders authorship in neither direction: a traceback the
supervisor emitted is supervisor-authored however it reached the record, and an
agent's inference is agent-authored however confidently it is phrased.

A diagnostic in a `loop` report — or an evidence sub-block within one (§2.9) —
may carry `origin: "supervisor_reported"` **iff both hold**:

1. `evidence.supervisor_detail` carries the **verbatim, unedited**
   supervisor-authored payload backing the claim: an error body or traceback
   returned in a tool result, or a field read from `verified.json` /
   `nxd://…/outputs`. Paraphrase, summary, or reconstruction disqualifies it.
2. `path` names the producing tool, so a reader can locate the payload — a
   `tool_path` per §1.6's grammar, e.g. `tool:build_data_product.error`. No other
   prefix is legal here; §1.6 is the whole vocabulary.

   **For a §2.9 evidence sub-block, `source` plays this role, not `path`** — a
   sub-block has no `path` field. `verified.json:evidence.model_tables` is a
   `source` value and is never a diagnostic `path`.

Otherwise `origin: "agent_observed"`. **When it is unclear, it is
`agent_observed`** — this is the fail-closed rule of §6.4 expressed as a field,
and it is load-bearing: an unbacked claim cannot reach `environment_suspect`
(§5.1) and therefore falls to `unsettled`, which is treated as `code_wrong`.
Misclassifying a real bug as "the environment" is what ships a broken DP flagged
green; the cost of the opposite error is a wasted heal attempt.

Two consequences worth stating, because they are what makes the design coherent
rather than aspirational:

- **`environment_suspect` and `retry_environmental` are reachable on the current
  supervisor.** A connection-refused error body returned verbatim by
  `build_data_product` at `s6_run` satisfies the criterion, so the environment
  path is live with no supervisor change. What the agent *cannot* produce is a
  supervisor-authored **stage attribution** — hence `pin.spec_compile_error`
  stays `origin: unbound` until a producer binds (§1.5 registry), and hence §6.3's
  warning that stage 4 masquerades as environment.
- **`evidence.supervisor_detail` is the reserved key *for a diagnostic*.** It is
  the only place a diagnostic's verbatim supervisor payload may live, which is
  what lets `dp_diagnostics.py` check the criterion mechanically instead of
  trusting the label. A §2.9 evidence **sub-block** is the other form: it carries
  its verbatim payload in its own data fields and names its origin in `source`,
  with no `supervisor_detail` key. `BUILD_RECORD_SCHEMA` pins both shapes.
  `record append` rejects a diagnostic claiming `supervisor_reported` with an
  absent or empty `evidence.supervisor_detail`, and
  `test_build_record_schema.py` pins both the rejection and the reachability of
  `environment_suspect` through a satisfying fixture.

`validate_dp_spec.py --json` emits exactly this envelope, and it is the only
shape it emits.

### 1.8.2 `inspect_run` — the measured contract

`inspect_run` has been run against a real `nxd-desktop-supervisor` in an isolated
`--data-dir` (no Claude Desktop needed: `nxd-desktop-supervisor --data-dir <dir>
mcp serve` speaks stdio JSON-RPC to any client). What follows is measured, not
inferred. **It is not wired** — no step calls it and `origin: "unbound"` stays
until one does. Characterized is not the same as bound.

On a **failed** run, `inspect_run {run_id}` returns `run` with ~18 keys. The
load-bearing ones:

| key | why it matters |
|---|---|
| `stdout_tail` | the verbatim, unedited Python traceback — including the user transform's own file and line. This is the payload `evidence.supervisor_detail` requires. |
| `phases[]` | a timeline (`snapshot_compiled` → `transform_dispatched` → `child_reaped`) with `at_ms`/`duration_ms`. **The only truthful stage-attribution signal.** |
| `staging_present`, `marker_present`, `child_exit` | corroborate where the run died |
| `run_id`, `status` | durable identity; `Failed` vs `Published` |

A diagnostic built from that payload — `origin: supervisor_reported`,
`path: "tool:inspect_run.run.stdout_tail"`, traceback in
`evidence.supervisor_detail` — passes `validate_diagnostic()` with zero problems,
while dropping `supervisor_detail` or using a non-`tool:` path fails with the
§1.8.1 messages. **So `supervisor_reported` at `s6_run` is backable today.**

Boundary, and it is narrower than it looks:

- **s4_pin / s6_run / s7_publish are distinguishable** from `phases[]` plus
  `staging_present`/`child_exit`/`status`.
- **s5_serve is not.** Nothing in the payload speaks to post-publish serving.
- The supervisor emits **no** `code`/`stage`/`severity`/`owner`/`origin`. Stage
  attribution remains an *agent inference* over supervisor-authored evidence —
  §1.8.1's caveat holds.

Traps, each observed:

- `inspect_run {}` lists **failures only**; a successful run is invisible there
  and retrievable only by explicit `run_id`.
- On success the diagnostic fields are present but empty — `phases: []`,
  `error: ""`, and misleadingly `staging_present: false` on a run that published
  rows. **Never read those booleans as health**; use `list_data_products` or
  `status: "Published"`.
- An unknown `run_id` returns `{"recent": []}` with `isError: false` and **no
  `run` key** — indistinguishable from "no failures". Test for the key.
- The key set is outcome-dependent (failure has `timeout_phase`/`child_exit`;
  success has `release_basename`/`published_at_unix_ms`). Treat both as optional.
- `run.error` is a generic wrapper (`boot kernel against snapshot: …`) and can
  **name the wrong stage** — a transform crash at `transform_dispatched` reported
  a boot/serve failure. Trust `phases[]`, never the error string.
- A transform raising in ~1 ms cost **170 s** and surfaced through
  `build_data_product` as "did not materialize staging output", never naming the
  user exception. `inspect_run` is the only route to the real cause.

Not representable in the build record: `phases[]` (the best attribution signal
available) and `nxd-verification-v1` (per-table row counts + sha256, the
strongest s7 evidence). Both ride as ad-hoc `evidence` keys until the schema
grows a home for them.

### 1.9 JSON Schema (normative)

Ships as `<nxd-pocket-loop>/scripts/dp_diagnostics.py::DIAGNOSTIC_SCHEMA` and is emitted by
`python3 <nxd-pocket-loop>/scripts/dp_diagnostics.py schema --diagnostic`.

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "nxd-diagnostic-v1",
  "type": "object",
  "additionalProperties": false,
  "required": ["schema", "stage", "code", "severity", "owner", "origin", "path", "message"],
  "properties": {
    "schema":   { "const": "nxd-diagnostic-v1" },
    "stage":    { "enum": ["s0_spec", "s1_structure", "s2_transform", "s3_closure",
                           "s4_pin", "s5_serve", "s6_run", "s7_publish", "s8_answer"] },
    "code":     { "type": "string", "pattern": "^[a-z][a-z0-9_]*(\\.[a-z][a-z0-9_]*){1,2}$" },
    "severity": { "enum": ["error", "warning", "info"] },
    "owner":    { "enum": ["agent", "user", "environment"] },
    "origin":   { "enum": ["agent_observed", "supervisor_reported", "tool_computed",
                           "llm_authored", "unbound"] },
    "path":     { "type": "string" },
    "message":  { "type": "string", "minLength": 1 },
    "evidence": { "type": "object", "default": {} },
    "fix":      { "type": ["string", "null"] }
  }
}
```

---

## 2. The build record

### 2.1 Identity

- **File:** `build-record.json`, at the **closure root**.
- **Generated, never hand-authored.** No template, no prose sections to fill.
- **Travels with the closure** — it is what a cold reader and the export handoff
  read to learn what actually happened.
- Written and updated by `<nxd-pocket-loop>/scripts/dp_diagnostics.py record …` and, for stages
  1–3 only, by `self_check.py --record build-record.json`.

It carries **outcomes only**. The plan lives in the byte-copied spec snapshot;
nothing here duplicates it, and nothing here is hand-copied.

### 2.2 Lifecycle

1. **At generation**, before self-check: `record init` writes the envelope,
   `compiled_from`, `compiler_version`, and every stage as `not_reached` —
   **except `s0_spec`, which `record init` fills in the same pass** (see below).
2. **Step 7**: `self_check.py --json --record build-record.json` merges
   `s1_structure`, `s2_transform`, `s3_closure`. Phase C validates the record's
   own presence and `compiled_from` — so the record must exist *before* Phase C
   runs, which is why step 1 is unconditional.
3. **Stages 4–8** are merged by the loop as they happen, via `record append`.
4. Every heal / regenerate / remap appends to `attempts[]` **before** re-running.

**The `s0_spec` producer is `record init`.** Every stage needs exactly one
producer; an `s0_spec` with none would stay `not_reached` forever and make §5's
`materialized()` permanently false — a fully green, published product stuck at
`in_progress`. `record init` is the natural place: generation only happens
against an **approved, validated** spec, so the validator has necessarily been
run against exactly the bytes being snapshotted.

```
python3 <nxd-pocket-loop>/scripts/dp_diagnostics.py record init \
    --record <closure>/build-record.json \
    --lock   <closure>/dp-spec.lock.json \
    [--spec-report <report.json>]
```

- **Default (no `--spec-report`)**: `record init` runs the validator itself,
  in-process, against **`<closure>/dp-spec.approved.md`** — the snapshot, not the
  live IR, because the snapshot is what the closure was compiled from. It records
  the resulting `nxd-diagnostic-report-v1` as `stages.s0_spec`.
  **Import direction (do not get this wrong):** `validate_dp_spec` imports
  `dp_diagnostics` at module top (§8.2), so `dp_diagnostics` must **not** import
  `validate_dp_spec` at module top — that is a cycle. `record init` does the
  import **inside the function body**, by which point `dp_diagnostics` is fully
  loaded and already in `sys.modules`. When `record init` runs in a context where
  importing the validator fails, it falls back to requiring `--spec-report` and
  exits 2 with a message saying so, rather than writing `s0_spec: not_reached`
  and quietly recreating the hole this rule exists to close.
- **With `--spec-report`**: it ingests an already-emitted
  `nxd-diagnostic-report-v1` from `validate_dp_spec.py --json` instead of
  re-running it. The report's `spec_hash` **must** equal `lock.spec_hash`; a
  mismatch is a hard error (exit 2) — ingesting a report computed against
  different bytes would silently certify the wrong plan.

Status mapping, same rule as every other stage: no errors → `passed`; no errors
but ≥1 warning → `passed_with_warnings`; ≥1 error → `failed`. A `failed` `s0_spec`
means generation ran against a spec that does not validate, which
`spec.frontmatter.approved_with_errors` should already have caught at approval
time — recording it is how that failure becomes visible instead of implicit.

`record init` is the **only** writer of `s0_spec`; `record append --stage s0_spec`
is rejected. Re-validating after a write-back (§2.8) does not update it: `s0_spec`
describes the snapshot the closure was built from and is frozen with it. The live
IR having moved is `plan_moved` (§5.1), not an `s0_spec` regression.

A record whose later stages are `not_reached` is normal and honest. `not_reached`
is a distinct status from `passed` and from `failed`, exactly because
`self_check.py` exits on the first failing phase and later phases produce no
signal at all.

### 2.3 Envelope

```jsonc
{
  "schema": "nxd-build-record-v1",
  "workflow": "candidate-scoring",
  "data_product": "candidate_scoring",
  "closure_path": "/abs/path/to/closure",
  "compiled_from": "sha256:…",          // == dp-spec.lock.json spec_hash
  "compiler_version": {
    "plugin": "0.28.0",
    "generator_skill": "nxd-generate-dp",
    "dp_spec_version": 1,
    "canonicalization": "nxd-dp-spec-canon-v1"
  },
  "generated_at_unix_ms": 1769904000000,
  "generator_model": "claude-opus-5",
  "stages": { /* §2.4 */ },
  "attempts": [ /* §2.5 */ ],
  "concessions": [ /* §2.7 */ ],
  "blockers": [ /* §2.8 */ ],
  "readback": { /* §2.6 */ },
  "evidence": { /* §2.9 */ },
  "caps": { /* §2.10 */ },
  "narrative": { /* §2.11 */ }
}
```

### 2.4 `stages`

Keyed by the nine stage ids. Every key present at all times.

```jsonc
"s2_transform": {
  "status": "passed",           // passed | passed_with_warnings | failed
                                // | not_reached | skipped
  "ordinal": 2,
  "at_unix_ms": 1769904012345,
  "origin": "tool_computed",
  "diagnostics": [ /* nxd-diagnostic-v1 */ ],
  "detail": { "models_counted": 4, "unverified": 1 }
}
```

`skipped` is only legal for `s7_publish` (no static artifact requested) and
`s8_answer` (no query asked). It never applies to `s0`–`s6`.

### 2.5 `attempts[]` — the part that makes claims checkable

```jsonc
{
  "attempt": 3,
  "kind": "heal",               // generate | regenerate | remap | heal | retry
  "stage": "s2_transform",
  "started_at_unix_ms": 1769904030000,
  "origin": "agent_observed",
  "diagnosis": {
    "code": "runtime.assert_failed",
    "path": "closure:transform/main.py:214",
    "summary": "per-candidate uniqueness assert fired: 12 duplicate ids"
  },
  "changed": [
    { "file": "transform/main.py", "what": "deduplicate on ashby_candidate_id before the join" }
  ],
  "spec_hash_before": "sha256:…",
  "spec_hash_after":  "sha256:…",
  "rerun": {
    "stage": "s2_transform",
    "status": "passed",
    "diagnostics_cleared": ["runtime.assert_failed"],
    "diagnostics_new": []
  },
  "exit": "healed_with_concessions",
  "concessions": ["concession.assert_weakened"]
}
```

`exit` vocabulary: `healed`, `healed_with_concessions`, `caps_exhausted`,
`blocked`, `retry_environmental`.

**INVARIANT-D2 (mechanical).** For every attempt with
`kind ∈ {heal, retry, remap}`, `spec_hash_before == spec_hash_after`. A heal that
moved the hash edited the IR to make the build pass. That is a spec edit, and the
record writer rejects it: emit `blocker.spec_edit_required`, set
`exit: "blocked"`, and route it to the user for re-approval. This is the single
place where "a compiler does not edit your source" stops being advice.

`kind: "regenerate"` is the one kind allowed to carry different hashes — a
regenerate after an approved spec edit is exactly the legitimate path.

**ORDERING RULE (normative) — INVARIANT-D2 vs. the `open_questions` write-back.**
The one legitimate way a heal attempt moves the live hash is §2.8's write-back: a
build-time blocker is written into the live `dp-spec.md`'s `## open_questions`,
which un-approves the spec by design. Without an ordering rule, one implementer
computes `spec_hash_after` before the write-back and another after it — and the
second one fires `blocker.spec_edit_required`, which is an accusation that the
agent cheated, on a *correct* blocked exit. So:

> **The write-back is performed only AFTER the attempt has been recorded with
> `exit: "blocked"`.** Both `spec_hash_before` and `spec_hash_after` record the
> **pre-write-back** hash, and they are therefore equal — truthfully, because the
> attempt itself never edited the IR. The write-back is a **separate, separately
> recorded event**, carried by `blockers[].written_back` (§2.8), never by
> `attempts[]`.

The lifecycle is fixed: `heal.attempt_started` → the attempt fails on a blocker →
append the attempt with `exit: "blocked"` and equal hashes → append the
`blockers[]` entry → *then* edit the live IR → set `written_back: true`.

The consequence for §5: the live IR's hash now diverges from `lock.spec_hash`.
That divergence is a **`plan_moved` condition** — observable only via
`lock verify --spec` — and it must **never** surface as
`blocker.spec_edit_required`. The two are disjoint by construction, and this rule
is what makes them so: `blocker.spec_edit_required` means *an attempt's own hashes
differed*; `plan_moved` means *the live IR has moved away from the snapshot the
closure was built from*. A blocked-and-written-back run produces the second and
never the first. (§5.1 reports it as `needs_user` rather than `plan_moved`,
because the blocker outranks the divergence it caused; both appear in `why[]`.)

**Honest caveat on `attempts[]` (extending §2.11).** The entry as a whole is
`origin: agent_observed`, but two of its fields are not observations:
`diagnosis.summary` and `changed[].what` are **LLM prose** — the agent's account
of what it thought was wrong and what it did about it. `diagnosis.code`,
`diagnosis.path`, both hashes, `rerun` and `exit` are mechanical and checkable;
the two prose fields are not, and a consumer must not treat them as evidence. The
`origin` field stays at entry granularity for schema simplicity; this paragraph is
the disclosure, and `src/nxd-pocket-loop/reference/build-record.md` repeats it.

### 2.6 `readback` — the distribution read-back as DATA

```jsonc
"readback": {
  "distribution": [
    { "model": "scored_candidates", "column": "verdict",
      "values": [ { "value": "pass", "count": 812 }, { "value": "interview", "count": 44 } ],
      "uniform": false, "origin": "tool_computed" },
    { "model": "scored_candidates", "column": "gate_g1",
      "values": [ { "value": "UNKNOWN", "count": 856 } ],
      "uniform": true, "origin": "tool_computed" }
  ],
  "absent": [
    { "source": "verdict_thresholds", "column": "verdict",
      "declared_missing": ["different_role", "needs_more_info"], "origin": "tool_computed" }
  ]
}
```

`self_check.py` prints these lines for the human path; with `--json` it also emits
them as `semantic.distribution` / `semantic.uniform_column` /
`semantic.absent_vocabulary` diagnostics and merges them here. A `uniform: true`
entry with no matching explanation in `concessions[]` is what
`concession.readback_uniform_unexplained` exists for.

### 2.7 `concessions[]`

```jsonc
{
  "code": "concession.assert_weakened",
  "class": "discouraged",
  "stage": "s2_transform",
  "path": "closure:transform/main.py:214",
  "what": "kept the most recent row per candidate instead of failing on 12 duplicate ids",
  "why": "the source feed carries genuine duplicate applications",
  "alternative_rejected": "fail the build and surface the 12 rows",
  "attempt": 3,
  "disclosed": false,
  "at_unix_ms": 1769904031000,
  "origin": "llm_authored"
}
```

`class` is always `"discouraged"`. There is no `"forbidden"` concession: a
forbidden invariant is never taken, it is escalated as a `blocker.forbidden_*`.
The two-way split lives in §6.6.

`disclosed` flips to `true` only when the agent has actually said it to the user.
**A green run carrying an undisclosed concession is the worst state in the
design, because it reads as materialized** — so §5's predicate is false while any
`disclosed: false` remains.

### 2.8 `blockers[]`

A build-time blocker is an `open_questions` entry **discovered late**. There is
no second mechanism.

```jsonc
{
  "code": "blocker.open_question",
  "open_question_id": "fx_rates",
  "question": "Which EUR→USD rate, over what date range?",
  "blocks": ["total_opex"],
  "disposition": "blocked",       // blocked | deferred | answered
  "stage": "s6_run",
  "path": "spec:open_questions[fx_rates]",
  "discovered": "build_time",     // pre_build | build_time
  "written_back": true,           // written into the LIVE dp-spec.md
  "at_unix_ms": 1769904090000,
  "origin": "agent_observed"
}
```

`written_back: true` means the entry was added to the live `dp-spec.md`'s
`## open_questions`. **That un-approves the spec** — the canonical hash changes,
so `compiled_from` no longer matches the live IR and §5's predicate correctly
reports not-materialized. The elicitation contract is therefore a **loop**, not a
pre-build-only gate, and the same "needs your input" queue serves both.

**When the write-back happens, and which hash the attempt records**, is fixed by
§2.5's ORDERING RULE and is not optional: the attempt that discovered the blocker
is appended **first**, with `exit: "blocked"` and
`spec_hash_before == spec_hash_after == the pre-write-back hash`; only then is the
live IR edited and `written_back` set to `true`. The attempt did not edit the IR,
so recording equal hashes is the truthful record, and INVARIANT-D2 does not fire.
The resulting divergence between the live IR and `lock.spec_hash` is visible only
through `lock verify --spec` and is reported only as `plan_moved` (§5.1).

`written_back: false` is legal and means the blocker was raised but the live IR
has not been edited yet — the normal state between recording the blocker and
performing the write-back, and the state a crash leaves behind. A blocker with
`disposition: "blocked"` makes §5's predicate false either way, so nothing is
concealed by the gap; `written_back` records only whether the IR-side half
completed.

### 2.9 `evidence` — the T1 fields, each with its origin

Each sub-block carries its own `origin`, and **`origin` here means exactly what it
means on a diagnostic (§1.1) and is governed by the same §1.8.1 relay
criterion** — this record is agent-written, so a sub-block claiming
`supervisor_reported` must carry the verbatim supervisor payload it is quoting
and name its source in `source`. `published_row_counts` and `publish` below
qualify: both are fields read unedited out of `verified.json`, which is
supervisor-authored. `endpoint` and `static_artifact` do not — those are the
agent's own observations *about* supervisor output, so they are `agent_observed`
even though a supervisor was involved.

The distinction is not pedantry. §5.1 admits `environment_suspect` only on
supervisor-authored evidence, so a sub-block that overclaims its origin is a
route to retrying a closure that is genuinely broken.

```jsonc
"evidence": {
  "phase_b_row_counts": {
    "origin": "agent_observed",
    "note": "scratch DuckDB dry run — NOT the published product",
    "models": [ { "table": "scored_candidates", "row_count": 856 } ]
  },
  "published_row_counts": {
    "origin": "supervisor_reported",
    "source": "verified.json:evidence.model_tables",
    "models": [ { "dataset": "main", "table": "scored_candidates", "row_count": 856 } ]
  },
  "publish": {
    "origin": "supervisor_reported",
    "workflow": "candidate-scoring", "publish_seq": 3,
    "definition_id": "…", "artifact_id": "…", "run_id": "…",
    "compiler_id": "…", "published_at_unix_ms": 1769904100000,
    "trust": "artifact_verified", "artifact_status": "available"
  },
  "endpoint": { "origin": "agent_observed", "reachable": true, "described_models": 4 },
  "static_artifact": { "origin": "agent_observed", "status": "…", "path": "…", "publish_seq": 3 },
  "required_capture": {
    "origin": "agent_observed",
    "fields": [ { "field": "github_url", "required_by": "scored_candidates",
                  "missing_rows": 14, "sample_keys": ["a_812", "a_930"] } ]
  },
  "source_state": {
    "origin": "agent_observed",
    "cursor_field": "created_at", "watermark": "2026-07-30T00:00:00Z",
    "note": "SOURCE DATA STALENESS — a separate axis. Never participates in materialization."
  },
  "supervisor_detail": { "origin": "unbound",
    "note": "stage-4 traceback / per-attempt identity; producer not bound (inspect_run characterized but unwired — §1.8.2)" }
}
```

`phase_b_row_counts` and `published_row_counts` are **separate keys and must
never be merged**. One is a dry run against a temporary database; the other is
what shipped. Collapsing them would let a Phase B count stand in as evidence the
product has rows.

`source_state` is a separate axis. It is recorded because it is useful and
excluded from §5 because staleness is not a build outcome.

### 2.10 `caps`

```jsonc
"caps": {
  "remap_per_question": 2, "regenerate_total": 3, "retry_environmental_total": 3,
  "regenerates_used": 1,
  "remaps_used": { "q1": 2, "q3": 0 },
  "retries_used": 0,
  "exhausted": []
}
```

Counted from `attempts[]`, never estimated. This is what makes the caps at
`scheduling.md` and `nxd-generate-dp/SKILL.md` something the agent can check
rather than self-police.

`retry_environmental_total: 3` exists because §1.4's re-emission rule needs a
counter to fire on: an environmental retry consumes neither a remap nor a
regenerate (§6.7), so without it there is no bound at all on `kind: "retry"` and
no defined moment at which an environment failure becomes
`blocker.caps_exhausted`. It counts attempts with `kind: "retry"` and
`exit: "retry_environmental"`; on exhaustion, `"retry_environmental"` is appended
to `exhausted[]` and the next occurrence is re-emitted as
`blocker.caps_exhausted` with `owner: "user"`.

A cap is a **bound on retrying, not a verdict on the closure**: exhausting the
retry cap does not make the closure known-bad, so §5.1 still reports
`environment_suspect` where the evidence supports it — the user simply hears about
it instead of the agent looping silently.

### 2.11 `narrative` — the honest caveat

```jsonc
"narrative": {
  "origin": "llm_authored",
  "disclaimer": "The fields below are the generator's ANALYSIS. They are neither the approved plan nor a mechanical fact.",
  "incomplete_extraction": "…",
  "summary": "…"
}
```

Some of the record is necessarily LLM-authored prose — the "referenced in the
source but not extracted" judgement is generator analysis, not measurement. Say
so up front, in the record itself, rather than letting a reader assume the whole
file is mechanical. Every `narrative` field carries `origin: llm_authored`, and
consumers must not treat it as evidence.

### 2.12 JSON Schema

Ships as `<nxd-pocket-loop>/scripts/dp_diagnostics.py::BUILD_RECORD_SCHEMA`, emitted by
`dp_diagnostics.py schema --record`. It is a straight transcription of §2.3–2.11
with `additionalProperties: false` at every level, `required` on every key named
above, and `$ref`s to `nxd-diagnostic-v1` for the diagnostic arrays. A golden
record under `evals/tests/fixtures/` validates against it.

---

## 3. The lock file and the canonical hash

### 3.1 The two files

| file | contents | how produced |
|---|---|---|
| `closure/dp-spec.approved.md` | **byte-identical copy** of the live `dp-spec.md` at the moment of approval | `shutil.copyfile` — no rewriting, no reformatting, no normalization |
| `closure/dp-spec.lock.json` | the hash, the compiler version, the resolved refs | `dp_diagnostics.py lock write` |

Byte-identical matters: the snapshot is evidence, and evidence that was
reformatted on the way in cannot be compared.

### 3.2 Lock contents

```jsonc
{
  "schema": "nxd-dp-spec-lock-v1",
  "spec_hash": "sha256:9f2c…",            // canonical, semantic — §3.4
  "canonicalization": "nxd-dp-spec-canon-v1",
  "snapshot": "dp-spec.approved.md",
  "snapshot_sha256": "3ab1…",             // raw bytes of the copy — §3.3
  "spec_status_at_copy": "approved",
  "dp_spec_version": 1,
  "name": "candidate_scoring",
  "workflow": "candidate-scoring",
  "source_basename": "dp-spec.md",
  "compiler_version": {
    "plugin": "0.28.0",
    "generator_skill": "nxd-generate-dp",
    "self_check": "nxd-self-check-v1"
  },
  "copied_at_unix_ms": 1769904000000,
  "resolved_refs": [
    { "spec_ref": "prompts/score_candidate.md",
      "closure_path": "prompts/score_candidate.md",
      "sha256": "c41e…" }
  ]
}
```

`source_basename`, not a path. The lock deliberately carries **no path to the
live IR**: the workflow id plus the `…/nxd-pocket/<workflow>/dp-spec.md`
convention recovers it, and storing a `../`-shaped string inside the closure is
exactly the escaping pointer this design forbids.

### 3.3 Two hashes, two jobs

- `snapshot_sha256` — SHA-256 of the **raw bytes** of `dp-spec.approved.md`.
  Answers *"was the in-closure copy edited after it was written?"* Requires
  nothing but `hashlib`, so `self_check.py` can check it inside the closure.
- `spec_hash` — SHA-256 of the **canonical form** (§3.4). Answers *"did the plan
  change?"* Whitespace- and formatting-insensitive. Requires PyYAML.

**Within the closure, byte identity is sufficient.** The snapshot's bytes are the
exact bytes `spec_hash` was computed from, so if `snapshot_sha256` matches, the
snapshot's canonical hash is still `spec_hash` by construction. Canonical hashing
is only needed to compare against the **live** IR — which is outside the closure
by construction. That is why Phase C does the byte check and
`dp_diagnostics.py lock verify` does the canonical one (§3.5).

### 3.4 `nxd-dp-spec-canon-v1` — the canonicalization algorithm

Precise enough that two implementers produce the same hash. Implemented once, in
`<nxd-pocket-loop>/scripts/dp_diagnostics.py::canonicalize()`.

**Input:** the raw bytes of a `dp-spec.md`.

1. Decode UTF-8, strict. Failure → `spec.encoding.not_utf8`, exit 2.
2. Replace `\r\n` and lone `\r` with `\n`.
3. Apply Unicode **NFC** normalization to the whole text.
4. Split frontmatter/body with `dp_diagnostics.split_frontmatter` — the ONE
   definition, which `validate_dp_spec.py` imports rather than copies (§1.5.1),
   so the hash necessarily describes the document the validator judged (leading
   `---`, `text.split("---", 2)`). No frontmatter → exit 2.
5. `yaml.safe_load` the frontmatter into a mapping.
6. Split the body with `dp_diagnostics.split_sections`, likewise the one
   definition: on `## ` headings; the heading is lowercased and spaces become
   underscores; a later duplicate heading overwrites an earlier one; section
   bodies are `.strip()`ed. **Two consequences of that exact behaviour, stated so
   nobody "improves" on it:** (i) body text **before the first `## ` heading is
   dropped** — `split_sections` only buffers once `current is not None` — so a
   preamble paragraph between the frontmatter and the first section never reaches
   the canonical form and therefore **never moves the hash**; (ii) only `## `
   starts a section, so `### ` subheadings stay inside their parent section's body
   and are hashed as part of it.
7. For each section body, `yaml.safe_load` it. On `yaml.YAMLError`, the value is
   the **stripped raw string** — the same fallback the validator uses for prose
   sections.
8. Build `{"dp_spec_version": <int>, "frontmatter": <fm>, "sections": {<name>: <value>}}`.
9. Normalize the object recursively:
   - **Mappings**: keys coerced with `str()`; **sorted by UTF-8 byte sequence**.
     `str()` coercion can collide (a mapping carrying both `1` and `"1"`).
     Vanishingly unlikely in a real spec, but the winner must not be undefined:
     **the canonicalizer raises** on a post-coercion duplicate key rather than
     silently dropping a value, because a silent drop changes the hash of a spec
     whose content did not change. Pinned by
     `evals/tests/test_dp_spec_canonicalization.py`.
   - **Lists**: **order is preserved.** Order is semantic — criteria order,
     verdict band precedence, decisions order. Never sort a list.
   - **Strings**: replace every run of Unicode whitespace with a single `U+0020`,
     then strip. (Re-wrapping a YAML block scalar is not a plan change.)
   - **Numbers**: `bool` first (it is a subclass of `int`) → JSON `true`/`false`.
     `int` → int. `float`: `-0.0` → `0.0`; an integral float → the equivalent
     `int` (`1.0` → `1`); otherwise `format(x, ".10g")` as a **string**.
   - **`None`** → JSON `null`.
   - **`date` / `datetime`** (PyYAML auto-parses these) → `.isoformat()` string.
   - Anything else → `str(x)`.
10. Serialize:
    `json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode("utf-8")`.
11. `spec_hash = "sha256:" + hashlib.sha256(canonical_bytes).hexdigest()`.

**Normalized away (does NOT change the hash):** line endings; Unicode
composition form; trailing whitespace; blank-line runs; YAML re-wrapping and
block-scalar style; quoting style; mapping key order; YAML `#` comments (dropped
by `safe_load`); `1` vs `1.0`; heading case and `Open Questions` vs
`open_questions`; **any body text before the first `## ` heading** (step 6).

**Semantic (DOES change the hash):** every key and value; list order; section
presence and section names; prose section text after whitespace collapsing;
`status` — including `proposed → approved`.

`status` participating is deliberate. `compiled_from` names the *approved*
revision, and the tamper check ("hash ≠ approved hash means the spec was edited
after approval") only works if approval itself is part of the hashed content.

**Known, accepted collision: the hash erases the YAML *type* of a float-like
string.** Step 9 renders a non-integral `float` as `format(x, ".10g")` — a
string — so `weight: 0.25` and `weight: '0.25'` canonicalize identically and
hash identically, while the validator treats them differently (the quoted one is
`spec.criteria.bad_weight`). This is harmless rather than merely unlikely: the
invalid twin carries an error, an errored spec cannot reach `approved`
(`spec.frontmatter.approved_with_errors`), and nothing is snapshotted before
approval — so the two can never both be a *compiled_from*. Stated here so a
later reader does not discover it and assume it is a bug.

**Stability guard.** The canonicalizer pins `yaml.safe_load` behaviour. A PyYAML
major bump requires re-verifying the golden fixture.
`evals/tests/test_dp_spec_canonicalization.py` carries:

- the golden hash of the worked example in
  `src/nxd-pocket-loop/reference/dp-spec.md`, pinned as a literal.
  **Extraction rule (normative):** the fixture is the content of the **sole
  fenced block whose info string is exactly `markdown`** in
  `src/nxd-pocket-loop/reference/dp-spec.md` — the only ```` ```markdown ````
  fence in the file (every other fence is ```` ```yaml ```` or ```` ```bash ````).
  The test asserts **exactly one** such fence exists and fails loudly if a second
  appears, rather than silently hashing the first. Never key on line numbers;
  edits move them. Changing a byte of the worked example means updating the
  golden hash in the same commit;
- a **must-not-change** table (CRLF, trailing spaces, re-wrapped block scalar,
  reordered mapping keys, added comment, `0.25` → `0.250`);
- a **must-change** table (reordered criteria list, changed weight, changed
  anchor text, `status: proposed` → `approved`, removed section);
- the idempotence law `canonicalize(emit(canonicalize(x))) == canonicalize(x)`.

### 3.5 Verification split

| check | who runs it | why there |
|---|---|---|
| snapshot bytes match `snapshot_sha256` | `self_check.py` Phase C | `hashlib` only; runs inside the closure with a minimal interpreter |
| `spec_status_at_copy == "approved"` | `self_check.py` Phase C | JSON read |
| `build-record.compiled_from == lock.spec_hash` | `self_check.py` Phase C | JSON read |
| canonical hash of the snapshot == `lock.spec_hash` | `dp_diagnostics.py lock verify` | needs PyYAML |
| canonical hash of the **live** IR == `lock.spec_hash` | `dp_diagnostics.py lock verify --spec <path>` | the IR is outside the closure |

Phase C emits `closure.canonical_hash_deferred` (`severity: info`) naming the
`lock verify` command, so a reader of the JSON output can never mistake the byte
check for the canonical one. Step 7 runs **both** commands; `nxd-review-closure`
checks that both were run.

### 3.6 `prompt_ref` and the mirrored directory

`dp-spec.md` defines `judgments[].prompt_ref` as relative to **the IR file**, not
the closure. A byte copy therefore carries a path that would resolve outside the
closure — a dangling pointer by another name.

Resolution, at snapshot time:

- Every `prompt_ref` is resolved against the live IR's directory and the file is
  **copied into the closure at the same relative path** (`prompts/x.md` →
  `closure/prompts/x.md`). The relative path is preserved, so the byte-copied
  spec stays correct without being rewritten and the hash stays valid.
- Each copy is recorded in `resolved_refs[]` with its own sha256.
- An **absolute** or `../`-rooted `prompt_ref` is `closure.escaping_reference` at
  snapshot time and blocks generation. Fix the IR, do not rewrite the copy.

Phase C checks every `resolved_refs[].closure_path` exists with a matching
sha256 (`closure.resolved_ref_missing`).

---

## 4. The closure layout

### 4.1 Layout

```
…/nxd-pocket/<workflow>/
├── dp-spec.md                 HAND-EDITED. The live IR. Beside, never inside.
├── prompts/…                  HAND-EDITED. Referenced by judgments[].prompt_ref.
└── closure/                   ← build_data_product points here
    ├── dp-spec.approved.md    GENERATED  byte copy of the approved IR
    ├── dp-spec.lock.json      GENERATED  hash + compiler version + resolved refs
    ├── build-record.json      GENERATED  outcomes, attempts, concessions, blockers, readback
    ├── README.md              GENERATED  reopen recipe + credentials block ONLY
    ├── spec.py                GENERATED
    ├── models.py              GENERATED
    ├── transform/main.py      GENERATED
    ├── infra-profile.yaml     GENERATED  (+ host-side credential injection)
    ├── requirements.txt       GENERATED
    ├── data/…                 GENERATED / landed
    ├── prompts/…              COPIED     mirrors the IR's relative prompt_ref paths
    ├── contracts/<name>.md    GENERATED (LLM prose) — deferred-model contracts
    ├── .gitignore             GENERATED  when a source carries live credentials
    └── SENSITIVE              GENERATED  when a source carries live credentials
```

Nothing under `closure/` is hand-authored. `dp-spec.md` is the only file a user
edits, and it is outside. The pre-approval policy gate's bright line — "nothing
under `closure/`" — holds, because the byte copy happens **after** approval, at
generation.

### 4.2 Where each kind of context lives

| Kind of context | Home |
|---|---|
| Intent | `dp-spec.approved.md` `## intent` |
| Population & sample rule | `dp-spec.approved.md` `## population` + the `decisions` row |
| Per-field inference & determinism caveats | `dp-spec.approved.md` `## models[].fields[].derivation` + `## decisions` (`provenance`) |
| Required-capture fields — **plan** half | `dp-spec.approved.md` `models[].fields[].required_capture: true` |
| Required-capture fields — **outcome** half (observed missing rows) | `build-record.evidence.required_capture` |
| Derived-model contract for models still to build | `contracts/<name>.md`, plus `models[].deferred: true` in the spec |
| Reopen recipe | generated `closure/README.md` |
| Credentials (key **names** only) | generated `closure/README.md` credentials block; names come from `sources[].credential_keys` |
| Known blockers | `build-record.blockers[]` |

`closure/README.md` is generated, template-filled, and carries **only** the reopen
recipe and the credentials block — roughly 20 lines. It has no plan sections, no
outcomes, no rulings, and nothing to hand-copy. Phase C gates its existence
because the reopen recipe is the one thing a cold reader needs that is neither
plan nor outcome.

### 4.3 What Phase C checks

| # | Check | Code on failure |
|---|---|---|
| C1 | `dp-spec.approved.md` exists at the closure root | `closure.spec_snapshot_missing` |
| C2 | `dp-spec.lock.json` exists, parses, `schema == "nxd-dp-spec-lock-v1"` | `closure.lock_missing` / `closure.lock_unparseable` |
| C3 | sha256 of the snapshot's bytes == `lock.snapshot_sha256` | `closure.lock_snapshot_byte_mismatch` |
| C4 | `lock.spec_status_at_copy == "approved"` | `closure.lock_status_not_approved` |
| C5 | `build-record.json` exists, parses, `schema == "nxd-build-record-v1"` | `closure.build_record_missing` / `closure.build_record_invalid` |
| C6 | `build_record.compiled_from == lock.spec_hash` | `closure.build_record_hash_mismatch` |
| C7 | `README.md` exists at the closure root | `closure.readme_missing` |
| C8 | every `lock.resolved_refs[].closure_path` exists with a matching sha256 | `closure.resolved_ref_missing` |
| C9 | escape scan: no `../…​.md` reference. Scan list: `README.md`, `dp-spec.approved.md`, `spec.py`, `models.py`, `transform/main.py`, `contracts/*` | `closure.escaping_reference` |
| C10 | credential guard files | `closure.gitignore_missing`, `closure.sensitive_missing`, `closure.gitignore_not_naming_profile` |
| C11 | informational: names the `lock verify` command | `closure.canonical_hash_deferred` |

The snapshot **is** scanned by C9. A `../`-rooted markdown reference inside the
approved spec is a real dangling pointer, and the snapshot is where it would
land. No carve-outs are needed anywhere: the escape scan works because the IR is
*copied* rather than *pointed at*. `dp-spec.lock.json` and `build-record.json`
are JSON and are not in the scan list.

Phase C's success line is exactly (frozen string, §9):

```
phase C ok — approved spec snapshot + lock present, no closure-escaping contract references
```

---

## 5. The materialization predicate

`materialized` is **not** a status field on the spec. Adding one would put an
outcome back into the IR. It is a predicate computed over the lock, the build
record and — when reachable — the live IR.

```python
def materialized(lock, record, live_spec_hash=None) -> bool:
    return (
        lock_ok(lock)                                              # C1–C4, C8
        and record["compiled_from"] == lock["spec_hash"]
        and (live_spec_hash is None or live_spec_hash == lock["spec_hash"])
        and all(record["stages"][s]["status"] in ("passed", "passed_with_warnings")
                for s in ("s0_spec", "s1_structure", "s2_transform", "s3_closure",
                          "s4_pin", "s5_serve", "s6_run"))
        and record["stages"]["s7_publish"]["status"] in
                ("passed", "passed_with_warnings", "skipped")
        and record["stages"]["s8_answer"]["status"] != "failed"
        and all(c["disclosed"] for c in record["concessions"])
        and not any(b["disposition"] == "blocked" for b in record["blockers"])
        and all(a["spec_hash_before"] == a["spec_hash_after"]
                for a in record["attempts"]
                if a["kind"] in ("heal", "retry", "remap"))
    )
```

`evidence.source_state` never appears. Source-data staleness is a separate axis
and merging it would make a correctly-built product read as broken because its
input is a day old.

Every stage named in this predicate has exactly one writer — `s0_spec`:
`record init`; `s1`–`s3`: `self_check.py --record`; `s4`–`s8`: `record append`
from a `tool: "loop"` report. A stage with no writer would pin `materialized()` at
`false` forever and stick §5.1 at `in_progress` for a green, published product.

The last clause restates INVARIANT-D2 as a materialization condition, and it is
satisfied by a correct blocked-and-written-back run: per §2.5's ORDERING RULE
those attempts carry **equal** hashes. Such a run is nonetheless not materialized
— it trips the `blockers[]` clause above, and §5.1 reports `needs_user`.

### 5.1 The distinguishable not-materialized states

Computed by `dp_diagnostics.py materialized --record … [--spec …]`, returned as
`{"materialized": false, "state": "<one of below>", "why": [...]}`.

| state | condition | what it means | what to do |
|---|---|---|---|
| `needs_user` | any blocker with `disposition: "blocked"` | | **ask** |
| `plan_moved` | `live_spec_hash != lock.spec_hash` | the plan changed after the build | **regenerate** |
| `code_wrong` | hashes match, an **offline** stage (`s0`–`s3`) failed | never environmental | **self-heal** |
| `unsettled` | hashes match, offline green, a stage ≥ `s4` failed without qualifying supervisor evidence | fail-closed | treat as `code_wrong` |
| `environment_suspect` | hashes match, offline green, **every** failing stage ≥ `s5` carries at least one error diagnostic and **all** of that stage's error diagnostics are `owner: environment` **and** `origin: supervisor_reported` per the §1.8.1 relay criterion | the closure is **not** known-bad | **retry** |
| `undisclosed_concession` | otherwise green, some `disclosed: false` | the worst state — reads as materialized | **disclose, then re-evaluate** |
| `awaiting_answer` | otherwise green, `s8_answer` failed | build is green, the answer is wrong | **refine** |
| `in_progress` | any required stage `not_reached` and nothing failed | | continue |

Order of evaluation is the table's order; the first matching state is reported.

**`environment_suspect` is decided PER FAILING STAGE, not over a flattened list.**
Every failing stage must **contribute** its own supervisor-authored evidence; a
stage that failed with an empty `diagnostics` list contributes nothing and
therefore disqualifies the whole run from `environment_suspect`, landing it in
`unsettled`. Evaluating a flattened list of every failing stage's diagnostics
instead would let a silent stage ride on a noisy one's evidence: a pure code bug
at `s4_pin` with no diagnostics attached, alongside a genuine environmental
failure at `s6_run`, would be reported as environmental and retried. Silence is
not evidence, and a stage nobody can vouch for must never read as environmental.
`_stage_is_environmental()` in `dp_diagnostics.py` is the per-stage test, and
`test_build_record_schema.py` pins both directions.

**`needs_user` outranks `plan_moved` deliberately.** The two co-occur on the
commonest path there is: a build-time blocker is written back into
`open_questions` (§2.8), which moves the live hash *as a consequence of* the
blocker. If `plan_moved` were reported first the agent would be told to
**regenerate** — against a spec that still carries the unanswered question that
stopped the build. The blocker is both the cause and the only useful next action,
so it is reported first. `why[]` still lists every matching condition, so the hash
divergence is never hidden — only deprioritized.

### 5.2 The label

Call it **`materialized`**. **Never `correct`.** `materialized` means the approved
plan was compiled, the compiled artifact ran, and it published. It says nothing
about whether the numbers are right. SELF-CHECK OK means the closure is
structurally sound and the transform ran, nothing more; never let a green exit
stand in for "the numbers are right".

---

## 6. The stage ladder and the failure taxonomy

### 6.1 The ladder

The vocabulary and the offline set are in §1.2. Classify a failure by **which
stage failed**, never by parsing exception text. The stages differ in what they
have access to; that difference is the classifier.

### 6.2 Stages 0–3 are offline and deterministic

A failure there is **never environmental**. Phase B in particular is the sharpest
instrument available for "a poorly generated DP that won't do its work": Phase B
executes for real, so what it reports is what will happen. A stage-2 failure is
unambiguously the code.

### 6.3 The three caveats

1. **Stage 4 masquerades as environment.** Phase A cannot execute the builders. A
   closure can pass Phase A in full and still fail when the supervisor pins it. A
   `build_data_product` failure is **not** presumptive evidence of a bad
   environment. `pin.build_failed` therefore ships with `owner: "agent"` in the
   registry, by construction rather than by evidence.
2. **Phase B covers only `transform/main.py`.** A green Phase B says nothing
   about `spec.py` or `models.py`, and its printed `unverified:` list is its own
   declared blind spot for dynamic constructs. Those lines are emitted as
   `struct.unverified` (`severity: info`) so the blind spot is in the record
   rather than in a scrollback.
3. **Stage 8 failures produce a fully green build.** The distribution read-back
   exists precisely to make them visible — a uniform classification column is the
   tell. It is non-gating; the build record records and surfaces it, adjacent to
   concessions (§2.6).

### 6.4 Classification fails closed

> When the evidence does not settle whether a failure is environmental, default
> to **not** environmental.

Misclassifying a real bug as "the environment" is what ships a broken DP flagged
green. The discriminating test is: **"would re-running this closure unchanged in
a healthy environment pass?"** Answering *yes* requires `supervisor_reported`
evidence. Absent that, the answer is *no*, `owner` is `agent`, and
`meta.classification_unsettled` is recorded so the honesty is visible.

### 6.5 Ownership classes and their handling

| class | `owner` | handling | typed exits |
|---|---|---|---|
| structural (`struct.`, `closure.`, `policy.`) | `agent` | must self-heal, bounded | `healed`, `healed_with_concessions`, `caps_exhausted`, `blocked` |
| runtime-user-code (`runtime.`) | `agent` | must self-heal, bounded | same |
| runtime-environment (`env.`, some `publish.`) | `environment` | retry, or ask for a credential; **does not count against materialization** | `retry_environmental` |
| blocker (`blocker.`, `spec.*` the agent must not invent) | `user` | write back into `open_questions`; the spec un-approves | `blocked` |
| concession (`concession.`) | `agent` | green **with a disclosed concession** | `healed_with_concessions` |

Bounds, counted from `attempts[]`, not estimated: **remap ≤ ~2 per question**,
**regenerate ≤ ~3 total**. Non-convergence must be reported, never looped on
silently, never abandoned silently.

### 6.6 The concession split

**FORBIDDEN — never do it even to get green. Escalate as a blocker instead.**
The invariants at `nxd-generate-dp/SKILL.md` are absolutes and a heal loop must
not be allowed to relitigate them:

- hand-writing `deployment-spec.yaml` / `manifest.yaml` / `models.yaml`
  → `blocker.forbidden_handwritten_yaml`
- hand-rolling a durable watermark instead of `transform_state`
  → `blocker.forbidden_manual_watermark`
- `write_disposition="replace"` while yielding a delta
  → `blocker.forbidden_replace_disposition`
- loosening an assert into restating its own arithmetic
  → `blocker.forbidden_assert_restates_arithmetic`
- reaching green only by changing the plan — narrowing the population to dodge a
  bad join, dropping a model whose grain won't resolve, relaxing a threshold
  → `blocker.spec_edit_required` (**this is a spec edit requiring re-approval,
  not a heal**; INVARIANT-D2 in §2.5 catches it mechanically)

**DISCOURAGED — permissible, but the run is green WITH A DISCLOSED CONCESSION**
recorded in `concessions[]` and surfaced to the user. The `concession.*` codes
in §1.5.

### 6.7 Typed heal exits

`healed` — re-run of the failing stage passed, no concession.
`healed_with_concessions` — passed, `concessions[]` grew, `disclosed` must flip
before anything is claimed.
`caps_exhausted` — the bound was reached; re-emit as `blocker.caps_exhausted`
with `owner: user` and report what was tried.
`blocked` — a blocker was hit; the user is asked, the spec un-approves. The
attempt is recorded **before** the `open_questions` write-back, with equal
`spec_hash_before`/`spec_hash_after` (§2.5 ORDERING RULE).
`retry_environmental` — the failure was `owner: environment` with
`supervisor_reported` evidence **satisfying the §1.8.1 relay criterion**;
consumes `caps.retry_environmental_total`, and never a remap or a regenerate. An
`owner: environment` failure whose evidence does *not* satisfy the criterion is
`agent_observed`, lands in `unsettled`, and is healed as code — never retried.

---

## 7. The middleman presentation rules

The builder agent is the middleman. The user does not need to know any of these
internals.

### 7.1 The rules

- **R1 — Two classes only.** The user hears about exactly two things:
  **BLOCKERS** ("I need something from you") and **CONCESSIONS** ("I did
  something you should know about"). Nothing else.
- **R2 — `owner`, not `severity`, decides.** A `severity: error` with
  `owner: agent` is absorbed. A `severity: warning` with `code: concession.*` is
  spoken. The field is the rule.
- **R3 — Everything else is one plain line of outcome.** Not a list of what
  went wrong and got fixed. One line.
- **R4 — Banned vocabulary.** Never say to the user: a stage number or name
  (`s2_transform`, "stage 4"), a phase letter ("Phase C"), a diagnostic code, a
  hash or `compiled_from`, `owner`, `origin`, `severity`, `provenance`,
  `not_reached`, "the IR", "canonicalization". Say what happened in the user's
  own vocabulary.
- **R5 — Never present green as right.** A green build is "built and checked",
  never "the numbers are correct".
- **R6 — A blocker is one sentence with the smallest possible ask**, plus what
  still works. Never a menu of internals; never a list of options the user did
  not ask for.
- **R7 — A concession states what was done, what it costs, and the alternative,
  in that order**, and offers to redo it.
- **R8 — Never assert "environment issue" without supervisor-reported evidence.**
  Say the honest thing instead. Fail-closed applies to speech as well as to
  classification.

### 7.2 Worked examples

**(a) Absorbed — the user hears one line of outcome.**

```json
{"stage":"s2_transform","code":"runtime.assert_failed","severity":"error",
 "owner":"agent","origin":"tool_computed",
 "path":"closure:transform/main.py:214",
 "message":"per-candidate uniqueness assert fired: 12 duplicate ashby_candidate_id",
 "evidence":{"count":12},"fix":"deduplicate before the join"}
```

The agent heals, re-runs, and says:

> Built and checked. 856 candidates scored, 7,704 criterion scores.

Not: which assert fired, that there was an attempt, that it was stage 2, or that
Phase B caught it. R3.

**(b) Blocker — `owner: user`, so the user hears it.**

```json
{"stage":"s6_run","code":"blocker.open_question","severity":"error",
 "owner":"user","origin":"agent_observed",
 "path":"spec:open_questions[fx_rates]",
 "message":"total_opex mixes EUR and USD invoices; no rate column exists in any source",
 "evidence":{"models":["total_opex"],"currencies":["EUR","USD"]},
 "fix":"ask for the rate source and date range"}
```

> I can't finish the total-spend figure: the invoices are in both euros and
> dollars and there's no exchange rate anywhere in the data. Which rate should I
> use, and over what date range? Everything else is built and you can query it
> now.

One ask, the smallest one, plus what still works. R6.

**(c) Concession — spoken, with the cost and the alternative.**

```json
{"code":"concession.assert_weakened","class":"discouraged","stage":"s2_transform",
 "path":"closure:transform/main.py:214",
 "what":"kept the most recent row per candidate instead of failing on 12 duplicate ids",
 "why":"the source feed carries genuine duplicate applications",
 "alternative_rejected":"fail the build and surface the 12 rows",
 "disclosed":false,"origin":"llm_authored"}
```

> One thing you should know: twelve candidates have more than one application in
> the feed, so the per-candidate uniqueness check wouldn't pass. I kept the most
> recent application for each and built on that — it drops twelve rows. If you'd
> rather see those twelve, I can make the build stop there instead.

`disclosed` flips to `true` only after this is said. Until then §5's predicate is
false. R7.

**(d) Unsettled — the honest thing, not "environment issue".**

```json
{"stage":"s4_pin","code":"pin.build_failed","severity":"error",
 "owner":"agent","origin":"agent_observed","path":"tool:build_data_product.error",
 "message":"build returned an error with no endpoint",
 "evidence":{"stdout_excerpt":"…"},"fix":null}
```

> The build didn't complete, and I can't yet tell whether that's my code or the
> machine — so I'm treating it as mine and taking another look at the
> definition.

Never "that's an environment problem". Stage 4 masquerades as environment
(§6.3), there is no supervisor-reported evidence here, and R8 applies.

---

## 8. Elicitation and UI prerequisites

The spec is an **elicitation contract**: from the user's point of view it
enforces getting enough information to successfully build a DP.
`validate_dp_spec.py` encodes the conditional requirements — criteria ⇒
verdicts; judgments ⇒ `rubric_version`; every gate ⇒ an `unknown:` rule; every
derived model ⇒ grain + key; every ruling-bearing section ⇒ a `decisions` row.
That is a progressive-disclosure form spec.

**The UI is rendered by the agent harness (e.g. Claude Desktop), not by the
supervisor.** The supervisor cannot do UI. Nothing in this section requires a
supervisor change. What the harness is owed is three things.

### 8.1 (a) Field-addressed diagnostics

Delivered by §1: `{path, code, severity, owner, control, …}` per finding, with
the identity-based path grammar of §1.6 and the per-code `control` hint of §1.5.
The **stable code** matters as much as the path — it is what lets a harness
render an anchors mapping editor for `spec.criteria.incomplete_scale` and a
number field for `spec.criteria.bad_weight`.

### 8.2 (b) A machine-readable schema

```
python3 <nxd-pocket-loop>/scripts/dp_diagnostics.py schema --json
```

emits:

```jsonc
{
  "schema": "nxd-dp-spec-schema-v1",
  "dp_spec_version": 1,
  "frontmatter": { "required": [...], "keys": { "status": {"enum": [...]}, ... } },
  "sections": [
    { "name": "criteria", "required": false, "kind": "list_of_mappings",
      "conditional_required_by": ["verdicts"],
      "entry": { "id": {...}, "weight": {"type": "number"}, "anchors": {...} } }
  ],
  "vocabularies": {
    "status": [...], "model_kinds": [...], "source_types": [...],
    "decision_status": [...], "decision_provenance": [...],
    "produced_by": [...], "reruns": [...], "dispositions": [...],
    "output_kinds": [...], "schedule_triggers": [...]
  },
  "codes": [ { "code": "...", "stage": "...", "severity": "...", "owner": "...",
               "control": "...", "agent_fillable": true, "summary": "..." } ]
}
```

**The vocabularies are emitted from the Python constants, never re-typed.** That
is structural rather than aspirational: `REQUIRED_SECTIONS`, `KNOWN_SECTIONS`,
`MODEL_KINDS`, `SOURCE_TYPES`, `DECISION_STATUS`, `DECISION_PROVENANCE`,
`PRODUCED_BY`, `RERUNS`, `DISPOSITIONS` and `STATUS_VALUES` live in
`<nxd-pocket-loop>/scripts/dp_diagnostics.py`, and `validate_dp_spec.py` imports them. One
definition, two consumers, no drift.

### 8.3 (c) A canonical emitter

Needed for the hash anyway (§3.4); the same component serves form round-trip and
readable diffs.

```
python3 <nxd-pocket-loop>/scripts/dp_diagnostics.py canonicalize <spec.md>   # canonical JSON to stdout
python3 <nxd-pocket-loop>/scripts/dp_diagnostics.py emit <canonical.json>    # markdown to stdout
```

Law: `canonicalize(emit(canonicalize(x))) == canonicalize(x)`.

**Trap:** the round trip is canonical, not byte-exact — comments, wrapping and
key order are lost. The emitter must therefore **never overwrite a hand-edited
`dp-spec.md` wholesale.** It writes a proposal the user reviews, or a targeted
edit. Silently reformatting the user's own file is the same class of failure as
silently correcting their values.

### 8.4 `provenance` as a rendering property, and the pre-fill trap

`provenance` is a rendering property: an agent-filled field renders as
**"proposed, unconfirmed"**, and the user confirming it is real evidence they saw
it. Approval moves `status`; it never moves `provenance`.

**THE TRAP, WRITTEN DOWN EXPLICITLY.** `dp-spec.md` forbids making the user
re-type into a template: *"Translate it; do not ask them to re-type it."* A
form-first UI regresses to forty empty fields — exactly the failure the IR was
designed to avoid.

> **RULE-PREFILL.** The agent **always** pre-fills from the conversation or the
> user's own document. The UI's job is **review-and-correct, never data entry.**
> A blank form is a fallback, never the entry point. `open_questions` is the only
> surface that should actively demand input.

Mechanization, so this is a rule and not an aspiration: **a blank is illegal in a
rendered form.** A field the agent has no basis for does not appear as an empty
control — it becomes an `open_questions` entry.
`spec.prefill.empty_required_field` (`warning`) fires when a required field is
*present but empty* rather than either filled (with `provenance`) or carried as
an open question.

---

## 9. Frozen strings — the cross-file contract

These literals appear in several files at once and must match exactly. Nothing
here may be paraphrased, pluralized or reordered.

**Closure filenames**
`dp-spec.approved.md` · `dp-spec.lock.json` · `build-record.json` · `README.md`

**Schema ids**
`nxd-diagnostic-v1` · `nxd-diagnostic-report-v1` · `nxd-build-record-v1` ·
`nxd-dp-spec-lock-v1` · `nxd-dp-spec-canon-v1` · `nxd-dp-spec-schema-v1`

**Stage ids**
`s0_spec` · `s1_structure` · `s2_transform` · `s3_closure` · `s4_pin` ·
`s5_serve` · `s6_run` · `s7_publish` · `s8_answer`

**Report `tool` values** (closed enum, §1.8)
`validate_dp_spec` · `self_check` · `dp_diagnostics` · `loop`

**Reference files**
`src/nxd-pocket-loop/reference/build-record.md` — the reader-facing normative doc
for §1, §2, §5 and §6.
`src/nxd-pocket-loop/reference/failure-handling.md` — the loop's operating
procedure over it (the ladder, fail-closed classification, typed exits, R1–R8).
`src/nxd-generate-dp/reference/closure-record.md` — how the generator emits the
record surfaces (byte copy, `prompt_ref` mirroring, lock write, `record init`,
the `README.md` and `contracts/<name>.md` templates).

**The verify-before-build closure file list** — must read identically in
`nxd-generate-dp/SKILL.md`, `scheduling.md`, `handoff-export.md`,
`nxd-review-closure/SKILL.md` and the eval checkers, and is pinned by
`test_closure_layout_gate.py`:

> `spec.py`, `models.py`, `infra-profile.yaml`, `transform/main.py`,
> `requirements.txt`, `dp-spec.approved.md`, `dp-spec.lock.json`,
> `build-record.json`, `README.md`, the connector companion artifact — and,
> for a credentialed source, `SENSITIVE` and `.gitignore`

**`self_check.py` stdout lines** — byte-exact; the deterministic-check wiring and
every scenario checker key on them:

```
phase A ok — …
phase B ok — …
phase C ok — approved spec snapshot + lock present, no closure-escaping contract references
phase D ok — …
SELF-CHECK OK — Phases A (structural), B (transform dry-run), C (context-completeness), D (policy boundary) all passed.
```

**Note the deliberate lie in that last literal.** Phase C verifies the byte-copied
spec snapshot, the lock, and the build record — not a context document's
completeness — but its *label* stays `C (context-completeness)` because the
string is byte-exact load-bearing. A comment at the emitting line in
`scripts/self_check.py` says so, or a later reader will helpfully "fix" the label
and silently break every checker that keys on it. Accuracy of the label loses to
stability of the contract; the comment is what keeps that trade visible.

**CLI surface**, all with `--json` and exit codes `0` ok / `1` findings /
`2` could not read:

```
python3 <nxd-pocket-loop>/scripts/dp_diagnostics.py hash        <spec.md>
python3 <nxd-pocket-loop>/scripts/dp_diagnostics.py canonicalize <spec.md>
python3 <nxd-pocket-loop>/scripts/dp_diagnostics.py emit        <canonical.json>
python3 <nxd-pocket-loop>/scripts/dp_diagnostics.py schema      [--json|--diagnostic|--record]
python3 <nxd-pocket-loop>/scripts/dp_diagnostics.py lock write  <spec.md> <closure-dir>
python3 <nxd-pocket-loop>/scripts/dp_diagnostics.py lock verify <closure-dir> [--spec <spec.md>]
python3 <nxd-pocket-loop>/scripts/dp_diagnostics.py record init   --record <path> --lock <path> [--spec-report <report.json>]
python3 <nxd-pocket-loop>/scripts/dp_diagnostics.py record append --record <path> [--stage <id>] --from <report.json>
python3 <nxd-pocket-loop>/scripts/dp_diagnostics.py record query  --record <path>
       [--stage …] [--owner …] [--severity …] [--code …] [--unresolved] [--attempt N]
python3 <nxd-pocket-loop>/scripts/dp_diagnostics.py materialized --record <path> [--lock <path>] [--spec <path>]
python3 scripts/self_check.py [--json] [--record build-record.json]
```

`record append` has two mutually exclusive routes, and mixing them is refused
with exit 2 rather than silently dropped: `--stage <id> --from <report.json>`
merges a stage's report, and `--evidence` writes a record-level
`evidence` sub-block (§2.9). `--evidence` takes no `--stage`, because an evidence
sub-block is not attached to a stage.

Style constraint: stdlib-only Python (PyYAML is already a dependency of
`validate_dp_spec.py` and may be used there), `argparse`, `--json`, meaningful
exit codes.

**CONSTRAINT-1 (the one that breaks the design if missed).** `self_check.py` is
**copied into the closure and run there**. It can **never** import
`dp_diagnostics.py`. It inlines a minimal literal vocabulary (a `dict` and
`json.dumps`), and `evals/tests/test_self_check_diagnostic_vocab.py` asserts that
every code and stage literal in `scripts/self_check.py` exists in
`dp_diagnostics.CODES`. Any attempt to share code by import is wrong.

**CONSTRAINT-2.** `self_check.py`'s **default** (no-flag) stdout must remain
prose and must keep the four `ok` lines above, because `evals/run.py`'s
deterministic-check fact and every scenario checker key on stdout. `--json`
changes nothing about the default path.

**CONSTRAINT-3.** `self-check.md` must keep **exactly one** `# self_check.py`
python fence (pinned by `test_self_check_sync.py`), that fence must remain the
**longest** python fence in the file, and it must keep the literals
`derrors = []` and `if derrors:` (sliced by `test_policy_boundary_phase_d.py`).

---

## 10. Design boundaries

Deliberate limits. Each is a decision, not an oversight.

- **One whole-spec hash; no per-section hashing.** The "what each section compiles
  to" relation is **many-to-many fan-in, not a DAG** — `nxd_decisions` is fed by
  population, gates, criteria, verdicts and open questions; a criteria change
  cascades through `rubric_version` into judgments. With an LLM doing codegen,
  partial regeneration also risks breaking the `PHYSICAL_MODELS` naming
  invariant, which spans `models.py`, `spec.py` and the transform. The
  section-to-artifact table in `reference/dp-spec.md` is a review aid, never a
  rebuild graph.
- **No supervisor changes.** Everything here is in-repo. Stage-4 detail,
  per-attempt identity and the supervisor traceback ship as **schema without a
  bound producer** (`origin: "unbound"`). `inspect_run` is characterized (§1.8.2)
  but not wired; `unbound` stays correct until a producer is actually bound.
- **The live IR stays beside the closure.** The pre-approval policy gate keeps
  its bright line ("nothing under `closure/`"), drafting history and rejected
  options stay out of handoffs, and the byte copy happens after approval.
- **No `materialized` status value on the spec.** `status` stays
  `draft | proposed | approved`. Materialization is a **derived predicate** over
  the lock and the build record (§5). Putting it in the spec would put an outcome
  back into the IR.
- **The distribution read-back does not gate.** It is recorded as data and
  surfaced next to concessions; it never fails a run.
- **Source-data staleness is not part of materialization.** `transform_state`
  freshness is a separate axis, recorded in `evidence.source_state` and excluded
  from the predicate.
- **No UI in this repo.** The three prerequisites the harness needs ship
  (field-addressed diagnostics, the machine-readable schema, the canonical
  emitter); nothing that renders.
- **`validate_dp_spec.py --json` emits one shape.** `nxd-diagnostic-report-v1`,
  with no legacy-shape fallback — carrying two shapes invites drift.

### Known gaps

- **`phases[]` and `nxd-verification-v1` have no home in the build-record
  schema.** They are the strongest attribution and s7 evidence available
  (§1.8.2), and currently ride as ad-hoc `evidence` keys.
- **`s5_serve` has no attribution producer.** Nothing in the `inspect_run`
  payload distinguishes post-publish serving, so a serve failure cannot be
  attributed to `s5_serve` from supervisor-authored evidence.
- **Transform logic is not fully captured by the IR.** The spec carries the
  *what* — `population` (the filter), `models[].fields[].derivation` (per-field
  extraction), `models[].grain`/`key` (the Tier-1 assert), `schedule` (the
  incremental route and cursor). It carries no **join logic, aggregation logic,
  or order of operations between models**: there is no section stating that a
  derived model is built by joining A to B on key K and then grouping by G.
  Where two models can be combined in more than one way, `nxd-generate-dp`
  chooses at codegen time and the spec never records the choice.

  This weakens the pipeline claim in §0 at its centre. "The closure is a pure
  function of the IR" holds for everything the IR names, but two regenerations
  from a byte-identical spec can emit different transforms without moving the
  spec hash — so a re-run is not reproducible in the way the hash implies, and
  a review of the spec cannot catch a wrong join. The compile table's warning
  that the fan-in is "many-to-many rather than a DAG" is a symptom of the same
  hole.

  Closing it means a transform-logic section (joins, aggregations, and their
  ordering) with validator coverage, which is a larger change than any single
  PR that has touched this file so far. Until then, the join a closure
  implements is reviewable only in `transform/main.py` — that is, in the
  generated artifact rather than in the approved plan.

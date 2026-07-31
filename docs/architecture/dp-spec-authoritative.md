# The spec is authoritative — design note

Status: **settled design, ready to implement.** This is the coordination artifact
for five parallel workstreams. Where it is ambiguous, five implementations
diverge — so it specifies shapes, names and literals rather than intentions.
Nothing here is up for relitigation; the decisions it encodes (D1–D11) were
taken before it was written. Where a decision has a rationale worth carrying,
the rationale is stated once and not repeated.

## Contents

- [0. What changes, in one paragraph](#0-what-changes-in-one-paragraph)
- [1. The unified diagnostic record (D9)](#1-the-unified-diagnostic-record-d9)
- [2. The build record (D8)](#2-the-build-record-d8)
- [3. The lock file and the canonical hash (D3)](#3-the-lock-file-and-the-canonical-hash-d3)
- [4. The closure layout after this change (D1)](#4-the-closure-layout-after-this-change-d1)
- [5. The materialization predicate (D5)](#5-the-materialization-predicate-d5)
- [6. The stage ladder and the failure taxonomy (D6, D7)](#6-the-stage-ladder-and-the-failure-taxonomy-d6-d7)
- [7. The middleman presentation rules (D11)](#7-the-middleman-presentation-rules-d11)
- [8. Elicitation and UI prerequisites (D4)](#8-elicitation-and-ui-prerequisites-d4)
- [9. Frozen strings — the cross-workstream contract](#9-frozen-strings--the-cross-workstream-contract)
- [10. File-by-file change manifest](#10-file-by-file-change-manifest)
- [11. What we are explicitly NOT doing](#11-what-we-are-explicitly-not-doing)

---

## 0. What changes, in one paragraph

`CONTEXT.md` is retired. The live, hand-edited `dp-spec.md` stays **beside** the
closure; at generation time the approved spec is **byte-copied into** the closure
as `dp-spec.approved.md` next to a `dp-spec.lock.json` carrying its canonical
hash and the compiler version. Build **outcomes** leave the IR entirely and
become a generated `build-record.json`. Self-containment stops being a prose
discipline ("copy, never point") and becomes a hash-checkable snapshot. Every
producer in the pipeline — `validate_dp_spec.py`, `self_check.py`, the build
loop — emits the **same** diagnostic shape, differing only in which stage
produced it.

The compiler framing that makes all of this fall out: **user intent is the
source, `dp-spec.md` is the IR, `nxd-generate-dp` is codegen, the closure's
Python is the output artifact.** Two consequences are load-bearing throughout:

1. An IR is a pure function of its source, so outcomes cannot live in it.
2. **A compiler does not edit your source to make the build pass.** The self-heal
   loop may change generated code; it may **never** change the IR. Reaching green
   by narrowing the population, dropping a model whose grain won't resolve, or
   relaxing a threshold is a **spec edit requiring re-approval**, not a heal.
   §2 makes this mechanically checkable.

---

## 1. The unified diagnostic record (D9)

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

`origin` is not in the original D9 field list; it is required here because D6
fails closed. An agent-inferred field is visibly weaker evidence than a
supervisor-reported one, and the classifier must be able to see the difference
without parsing prose. `unbound` means *the schema defines this field and no
producer exists yet* — that is how stage 4 detail is carried until a supervisor
binds it.

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
are exhausted" was undefined for an environmental failure: the remap and
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

The registry is **`scripts/dp_diagnostics.py::CODES`**, a mapping
`code -> {stage, severity, owner, control, agent_fillable, summary}`. Producers
supply `code` plus per-instance `path`/`message`/`evidence`.

**`severity` is registry-default and producer-overridable, downward only** — a
producer may relax `error` to `warning`, never the reverse.

**`owner` is NEVER producer-overridable.** It comes from the registry and only
from the registry. A diagnostic whose ownership changes is **re-emitted under a
new code**, never mutated in place — which is already how the design handles the
one legitimate ownership transition (`environment` → `user` becomes
`blocker.caps_exhausted`, §1.4), and follows directly from "a changed meaning is
a new code" above.

The asymmetry is deliberate, and it is not stylistic. `owner` is the field that
decides whether the human hears about a diagnostic at all (§7) and how a failure
counts against materialization (§5.1). A producer-relaxed `severity` costs a
warning; a producer-demoted `owner` silences a blocker. `dp_diagnostics.py`
rejects any report whose diagnostic carries an `owner` differing from its
registry entry, and `test_dp_diagnostics_schema.py` pins that rejection.

`control` exists for D4's UI (§8): it tells a harness which form control to
render for a spec-addressed error. Values: `text`, `long_text`, `number`,
`enum`, `list`, `mapping`, `table`, `confirm`, `none`.

#### Domain `spec.` — stage `s0_spec`, produced by `validate_dp_spec.py`

Every existing check in `validate_dp_spec.py` maps to exactly one code. This is
the complete v1 registry for that file; WS1 produces exactly these, no more.

**Completeness is enforced, not asserted** (§1.5.1). The table below was built by
walking every `report.error(...)` / `report.warn(...)` call site in
`scripts/validate_dp_spec.py`; a line-anchored reference is given in the
`replaces` column wherever the mapping is not obvious from the message text. WS1
ships a test that makes the claim mechanical rather than editorial.

| code | sev | owner | control | agent-fillable | replaces |
|---|---|---|---|---|---|
| `spec.encoding.not_utf8` | error | agent | none | no | (new, exit 2) |
| `spec.frontmatter.unparseable` | error | agent | none | yes | **`:105-115` raise → `:750-754`** — all three `split_frontmatter` `ValueError`s |
| `spec.frontmatter.missing_key` | error | agent | text | yes | missing required key |
| `spec.frontmatter.bad_version` | error | agent | number | yes | `dp_spec_version` mismatch |
| `spec.frontmatter.bad_name` | error | agent | text | yes | name not snake_case |
| `spec.frontmatter.bad_status` | error | user | enum | no | status not in vocabulary |
| `spec.frontmatter.approved_with_errors` | error | user | confirm | no | approved while errors hold |
| `spec.frontmatter.rubric_version_missing` | error | user | text | no | judgments without `rubric_version` |
| `spec.section.missing` | error | agent | none | yes | missing required section |
| `spec.section.empty` | error | agent | none | yes | required section empty |
| `spec.section.unknown` | warning | agent | none | no | unknown `##` heading |
| `spec.section.unparseable` | error | agent | long_text | no | YAML parse failure |
| `spec.source.no_entries` | error | agent | table | yes | **`:199-201`** `[sources] no source entries` |
| `spec.source.not_mapping` | error | agent | mapping | yes | **`:206-208`** `[sources][i] is not a mapping` |
| `spec.source.bad_type` | error | agent | enum | yes | type not in `SOURCE_TYPES` |
| `spec.source.no_location` | error | user | text | no | |
| `spec.source.no_scope` | error | user | long_text | no | |
| `spec.source.credential_value` | error | user | none | no | credential VALUE in the file |
| `spec.source.credential_key_mapping` | error | user | none | no | **`:226-233`** `credential_keys`/`credentials` carries a mapping — see the owner note below |
| `spec.source.label_missing` | error | agent | text | yes | 2+ sources, no label |
| `spec.source.label_duplicate` | error | agent | text | yes | |
| `spec.population.not_mapping` | error | agent | mapping | yes | |
| `spec.population.prose` | warning | agent | mapping | yes | prose instead of a mapping |
| `spec.population.missing` | error | user | long_text | no | no `population:` |
| `spec.model.no_entries` | error | agent | table | yes | **`:275-277`** `[models] no model entries` |
| `spec.model.no_name` | error | agent | text | yes | |
| `spec.model.bad_name` | error | agent | text | yes | not snake_case |
| `spec.model.bad_kind` | error | agent | enum | yes | |
| `spec.model.no_description` | error | agent | long_text | yes | |
| `spec.model.no_grain` | error | user | long_text | no | |
| `spec.model.no_key` | error | user | list | no | |
| `spec.model.duplicate_name` | error | agent | text | yes | |
| `spec.model.unmotivated` | warning | agent | list | yes | derived model, empty `answers` |
| `spec.gate.not_mapping` | error | agent | mapping | yes | **`:331-333`** `[gates][i] is not a mapping` |
| `spec.gate.no_rule` | error | user | long_text | no | |
| `spec.gate.no_unknown` | error | user | enum | no | |
| `spec.gate.unknown_is_fail` | error | user | enum | no | absence is never a judgement |
| `spec.criteria.no_entries` | error | agent | table | yes | |
| `spec.criteria.no_weight` | error | user | number | no | |
| `spec.criteria.bad_weight` | error | user | number | no | |
| `spec.criteria.weights_unbalanced` | error | user | table | no | sum ≠ 1.0 ±0.001 |
| `spec.criteria.no_scale` | error | user | mapping | no | |
| `spec.criteria.bad_scale` | error | user | mapping | no | min ≥ max, non-int |
| `spec.criteria.no_anchors` | error | agent | mapping | yes | |
| `spec.criteria.incomplete_scale` | error | agent | mapping | yes | **the flagship gap** |
| `spec.criteria.anchor_out_of_range` | error | agent | mapping | yes | |
| `spec.criteria.bad_provenance` | error | agent | enum | yes | |
| `spec.verdict.missing` | error | agent | table | yes | criteria present, verdicts absent |
| `spec.verdict.not_mapping` | error | agent | mapping | yes | |
| `spec.verdict.no_values` | error | user | list | no | |
| `spec.verdict.band_no_verdict` | error | agent | text | yes | |
| `spec.verdict.band_unknown_verdict` | error | agent | enum | yes | |
| `spec.verdict.band_unreachable` | error | user | mapping | no | neither `min_score` nor `rule` |
| `spec.verdict.value_unreached` | error | user | table | no | declared verdict no band reaches |
| `spec.verdict.no_precedence` | error | user | long_text | no | |
| `spec.judgment.no_entries` | error | agent | table | yes | |
| `spec.judgment.no_model` | error | agent | text | yes | |
| `spec.judgment.bad_produced_by` | error | agent | enum | yes | |
| `spec.judgment.no_generator_model` | error | agent | text | yes | |
| `spec.judgment.no_rubric_version` | error | agent | text | yes | |
| `spec.judgment.bad_reruns` | error | agent | enum | yes | |
| `spec.judgment.evidence_disabled` | error | user | confirm | no | `evidence_required: false` |
| `spec.schedule.not_mapping` | error | agent | mapping | yes | |
| `spec.schedule.bad_trigger` | error | agent | enum | yes | |
| `spec.schedule.no_cron` | error | user | text | no | |
| `spec.schedule.no_cursor_field` | error | user | text | no | |
| `spec.schedule.regrain_not_append_safe` | warning | user | confirm | no | |
| `spec.output.not_mapping` | error | agent | mapping | yes | **`:565-567`** `[outputs][i] is not a mapping` |
| `spec.output.no_name` | error | agent | text | yes | |
| `spec.output.unknown_model` | error | agent | enum | yes | |
| `spec.output.bad_kind` | error | agent | enum | yes | |
| `spec.decision.no_id` | error | agent | text | yes | |
| `spec.decision.bad_status` | error | agent | enum | yes | |
| `spec.decision.bad_provenance` | error | agent | enum | yes | |
| `spec.decision.no_ruling` | error | user | long_text | no | |
| `spec.decision.blocked_with_applies_to` | error | agent | none | yes | |
| `spec.decision.no_applies_to` | error | agent | list | yes | |
| `spec.decision.duplicate_id` | error | agent | text | yes | |
| `spec.decision.missing_for_ruling` | error | agent | table | yes | rulings exist, no ledger |
| `spec.decision.ruling_uncovered` | warning | agent | table | yes | no row mentions a ruling section |
| `spec.decision.sample_rule_unrecorded` | error | agent | table | yes | |
| `spec.open_question.not_mapping` | error | agent | mapping | yes | |
| `spec.open_question.no_question` | error | agent | long_text | yes | |
| `spec.open_question.bad_disposition` | error | agent | enum | yes | |
| `spec.open_question.answered_without_decision` | warning | agent | table | yes | |
| `spec.question.unanswered` | warning | agent | list | yes | question no model answers |
| `spec.approval.agent_authored_at_approved` | warning | user | confirm | no | |
| `spec.prefill.empty_required_field` | warning | agent | none | yes | **new** — see §8.4 |

#### 1.5.1 Keeping the `spec.` registry complete — by construction

Three things make the completeness claim above true rather than merely stated.

**(i) The two many-to-one codes, enumerated.** Every other code has exactly one
call site. These two do not, and the discriminator is `evidence.reason` — a
closed enum, so no implementer invents a third code for a variant:

| code | call sites | `evidence.reason` |
|---|---|---|
| `spec.frontmatter.unparseable` | `:108` / `:111` / `:114`, all surfaced at `:753` | `missing` (no leading `---`) · `unterminated` (no closing `---`) · `not_mapping` (frontmatter is not a YAML mapping) |
| `spec.criteria.bad_scale` | `:383-384` / `:386-387` | `non_integer` (min/max not `int`) · `min_not_below_max` |

Both are fatal to further parsing at their own level: `spec.frontmatter.unparseable`
returns the report immediately (`:754`), and `spec.criteria.bad_scale` `continue`s
past the anchor checks for that criterion. Producers must not synthesize the
downstream diagnostics that were never reached — a not-reached check emits
nothing, exactly as at the stage level (§2.2).

**(ii) The `spec.source.credential_key_mapping` owner is `user`, deliberately.**
Structurally the agent could repair it (drop the value, keep the key name), which
would argue for `owner: agent`. It is `owner: user` for the same reason
`spec.source.credential_value` is: the shape that triggers it is a mapping whose
*value* is a live secret sitting in a shareable file. Only the user can decide
whether that secret must now be rotated, and silently rewriting the file would
erase the evidence that it leaked. Fail closed, and let the user hear it (§7).

**(iii) WS1 ships `evals/tests/test_validator_code_coverage.py`, which makes this
mechanical.** The table above is documentation; the test is the contract:

- every `report.error(` / `report.warn(` call site in `scripts/validate_dp_spec.py`
  passes a `code=` argument (AST walk over the `Call` nodes — a call site with no
  `code=` fails the test);
- every such literal is a key in `dp_diagnostics.CODES` whose registry `stage` is
  `s0_spec`;
- **and the converse**: every `spec.*` key in `CODES` is emitted by at least one
  call site, with **one declared exemption**: `spec.encoding.not_utf8` is raised
  at the file-read boundary (`:748`) and exits 2 before a `Report` exists, so it
  is emitted outside the `report.error` path. It is listed by name in the test as
  the sole exemption — never a pattern, never a prefix, so a second uncovered code
  cannot slip in behind it. This is the direction that catches a dropped check — a code in the
  registry that nothing produces means a check went missing on the way in.

Adding a check to `validate_dp_spec.py` therefore *requires* adding a code, and
deleting a check *requires* deleting its code. Neither can happen silently, and
the "no check dropped, no code invented" constraint stops depending on five
implementers reading this table carefully.

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

| code | sev | owner | replaces / new |
|---|---|---|---|
| `closure.spec_snapshot_missing` | error | agent | **replaces** `CONTEXT.md is missing` |
| `closure.lock_missing` | error | agent | new |
| `closure.lock_unparseable` | error | agent | new |
| `closure.lock_snapshot_byte_mismatch` | error | agent | new (tamper) |
| `closure.lock_status_not_approved` | error | user | new |
| `closure.build_record_missing` | error | agent | new |
| `closure.build_record_invalid` | error | agent | new |
| `closure.build_record_hash_mismatch` | error | agent | new |
| `closure.readme_missing` | error | agent | new (reopen recipe) |
| `closure.resolved_ref_missing` | error | agent | new (`prompt_ref` mirror) |
| `closure.escaping_reference` | error | agent | unchanged behaviour |
| `closure.gitignore_missing` | error | agent | unchanged |
| `closure.sensitive_missing` | error | agent | unchanged |
| `closure.gitignore_not_naming_profile` | error | agent | unchanged |
| `closure.canonical_hash_deferred` | info | agent | new — see §3.5 |
| `policy.decisions_not_base_model` | error | agent | unchanged |
| `policy.decisions_csv_missing` | error | agent | unchanged |
| `policy.decisions_column_missing` | error | agent | unchanged |
| `policy.decisions_value_out_of_vocab` | error | agent | unchanged |
| `policy.literal_duplicates_landed_value` | error | agent | unchanged |

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
column is the tell that a green build will answer wrongly. It stays non-gating,
and the build record must **record and surface** it adjacent to concessions
(§2.6). Recording it is the change; failing on it is not.

#### Domain `pin.` — stage `s4_pin`

`pin.build_failed` (`error` / **`agent`** / `origin: agent_observed`),
`pin.spec_compile_error` (`error` / `agent` / `origin: supervisor_reported`, no
producer today → `origin: unbound`), `pin.no_endpoint` (`error` / `agent`).

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
the same `CREDENTIAL_VALUE_RE` that `validate_dp_spec.py` already uses, replacing
a match with `<redacted>`. A check that prints the secret it found turns a
contained file leak into a transcript leak.

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
| `validate_dp_spec` | `scripts/validate_dp_spec.py --json` | `s0_spec` |
| `self_check` | `scripts/self_check.py --json` | `s1_structure`, `s2_transform`, `s3_closure` |
| `dp_diagnostics` | `scripts/dp_diagnostics.py` (`lock verify`, `materialized`) | any |
| `loop` | **the agent**, hand-constructed from tool results | `s4_pin` … `s8_answer` |

`loop` exists because stages 4–8 have no script producer — the agent observes a
`build_data_product` error or a `list_data_products` row count and constructs the
report itself. Naming that honestly matters: a `loop` report is agent-constructed
and is **visibly weaker evidence** than a `tool_computed` report. Labelling it
`dp_diagnostics` would disguise an observation as a measurement, which is exactly
the fail-closed posture of D6 inverted. `record append --stage <s4…s8> --from
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
2. `path` names the producing tool (e.g. `mcp:build_data_product`,
   `verified.json:evidence.model_tables`), so a reader can locate the payload.

Otherwise `origin: "agent_observed"`. **When it is unclear, it is
`agent_observed`** — this is the D6 fail-closed rule expressed as a field, and it
is load-bearing: an unbacked claim cannot reach `environment_suspect` (§5.1) and
therefore falls to `unsettled`, which is treated as `code_wrong`. Misclassifying
a real bug as "the environment" is what ships a broken DP flagged green; the cost
of the opposite error is a wasted heal attempt.

Two consequences worth stating, because they are what makes the design coherent
rather than aspirational:

- **`environment_suspect` and `retry_environmental` are reachable today.** A
  connection-refused error body returned verbatim by `build_data_product` at
  `s6_transform` satisfies the criterion, so the environment path is live on the
  current supervisor with no supervisor change. What the agent *cannot* produce
  is a supervisor-authored **stage attribution** — hence `pin.spec_compile_error`
  stays `origin: unbound` until a producer binds (§1.5 registry), and hence D6's
  warning that stage 4 masquerades as environment.
- **`evidence.supervisor_detail` is the reserved key.** It is the only place a
  verbatim supervisor payload may live, which is what lets `dp_diagnostics.py`
  check the criterion mechanically instead of trusting the label.
  `record append` rejects a diagnostic claiming `supervisor_reported` with an
  absent or empty `evidence.supervisor_detail`, and
  `test_build_record_schema.py` pins both the rejection and the reachability of
  `environment_suspect` through a satisfying fixture.

`validate_dp_spec.py --json` emits exactly this. The old
`{spec, ok, errors[], warnings[]}` shape is **removed**, not deprecated: nothing
in the repo reads it (verified across `evals/`, `scripts/`, `.github/`), and
carrying both invites drift.

### 1.9 JSON Schema (normative)

Ships as `scripts/dp_diagnostics.py::DIAGNOSTIC_SCHEMA` and is emitted by
`python3 scripts/dp_diagnostics.py schema --diagnostic`.

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

## 2. The build record (D8)

### 2.1 Identity

- **File:** `build-record.json`, at the **closure root**.
- **Generated, never hand-authored.** No template, no prose sections to fill.
- **Travels with the closure** — it is what a cold reader and the export handoff
  read to learn what actually happened.
- Written and updated by `scripts/dp_diagnostics.py record …` and, for stages
  1–3 only, by `self_check.py --record build-record.json`.

**This is not `CONTEXT.md` renamed.** The five duplicated plan sections are gone
— the byte-copied spec carries them. The hand-copy discipline is gone. What
remains is outcome-only and mostly mechanical.

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

**The `s0_spec` producer is `record init`.** Every other stage has an obvious
producer and `s0_spec` had none, which would leave it `not_reached` forever and
make §5's `materialized()` permanently false — a fully green, published product
stuck at `in_progress`. `record init` closes that hole, and it is the natural
place: generation only happens against an **approved, validated** spec, so the
validator has necessarily been run against exactly the bytes being snapshotted.

```
python3 scripts/dp_diagnostics.py record init \
    --record <closure>/build-record.json \
    --lock   <closure>/dp-spec.lock.json \
    [--spec-report <report.json>]
```

- **Default (no `--spec-report`)**: `record init` runs the validator itself,
  in-process, against **`<closure>/dp-spec.approved.md`** — the snapshot, not the
  live IR, because the snapshot is what the closure was compiled from. It records
  the resulting `nxd-diagnostic-report-v1` as `stages.s0_spec`.
  **Import direction (WS1, do not get this wrong):** `validate_dp_spec` imports
  `dp_diagnostics` at module top (§8.2), so `dp_diagnostics` must **not** import
  `validate_dp_spec` at module top — that is a cycle. `record init` does the
  import **inside the function body**, by which point `dp_diagnostics` is fully
  loaded and already in `sys.modules`. `record init` also runs when the closure is
  generated in a context where importing the validator fails; in that case it
  falls back to requiring `--spec-report` and exits 2 with a message saying so,
  rather than writing `s0_spec: not_reached` and quietly recreating the hole this
  rule exists to close.
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
record writer must reject it: emit `blocker.spec_edit_required`, set
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
never the first. (§5.1 will report it as `needs_user` rather than `plan_moved`,
because the blocker outranks the divergence it caused; both appear in `why[]`.)

**Honest caveat on `attempts[]` (extending §2.11).** The entry as a whole is
`origin: agent_observed`, but two of its fields are not observations:
`diagnosis.summary` and `changed[].what` are **LLM prose** — the agent's account
of what it thought was wrong and what it did about it. `diagnosis.code`,
`diagnosis.path`, both hashes, `rerun` and `exit` are mechanical and checkable;
the two prose fields are not, and a consumer must not treat them as evidence. The
`origin` field stays at entry granularity for schema simplicity; this paragraph is
the disclosure, and `build-record.md` (WS3) must repeat it.

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

This replaces the current prose lines. `self_check.py` still prints them for the
human path; with `--json` it also emits them as `semantic.distribution` /
`semantic.uniform_column` / `semantic.absent_vocabulary` diagnostics and merges
them here. A `uniform: true` entry with no matching explanation in
`concessions[]` is what `concession.readback_uniform_unexplained` exists for.

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
The two-way split lives in §6.5.

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
    "note": "stage-4 traceback / per-attempt identity; producer not bound (inspect_run is a name only)" }
}
```

`phase_b_row_counts` and `published_row_counts` are **separate keys and must
never be merged**. One is a dry run against a temporary database; the other is
what shipped. Collapsing them would let a Phase B count stand in as evidence the
product has rows.

`source_state` is D3's separate axis. It is recorded because it is useful and
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

Counted from `attempts[]`, never estimated. This is what turns the prose caps at
`scheduling.md` and `nxd-generate-dp/SKILL.md` into something the agent can check
rather than self-police.

`remap_per_question: 2` and `regenerate_total: 3` are the repo's existing bounds,
now countable. **`retry_environmental_total: 3` is new** and exists because §1.4's
re-emission rule needs a counter to fire on: an environmental retry consumes
neither a remap nor a regenerate (§6.7), so before this there was no bound at all
on `kind: "retry"` and no defined moment at which an environment failure became
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

Ships as `scripts/dp_diagnostics.py::BUILD_RECORD_SCHEMA`, emitted by
`dp_diagnostics.py schema --record`. It is a straight transcription of §2.3–2.11
with `additionalProperties: false` at every level, `required` on every key named
above, and `$ref`s to `nxd-diagnostic-v1` for the diagnostic arrays. WS1 owns it;
a golden record under `evals/tests/fixtures/` must validate against it.

---

## 3. The lock file and the canonical hash (D3)

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
exactly the pointer this design removes.

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
`scripts/dp_diagnostics.py::canonicalize()`.

**Input:** the raw bytes of a `dp-spec.md`.

1. Decode UTF-8, strict. Failure → `spec.encoding.not_utf8`, exit 2.
2. Replace `\r\n` and lone `\r` with `\n`.
3. Apply Unicode **NFC** normalization to the whole text.
4. Split frontmatter/body exactly as `validate_dp_spec.split_frontmatter` does
   (leading `---`, `text.split("---", 2)`). No frontmatter → exit 2.
5. `yaml.safe_load` the frontmatter into a mapping.
6. Split the body exactly as `validate_dp_spec.split_sections` does: on `## `
   headings; the heading is lowercased and spaces become underscores; a later
   duplicate heading overwrites an earlier one; section bodies are `.strip()`ed.
   **Two consequences of copying that function exactly, stated so nobody
   "improves" on it:** (i) body text **before the first `## ` heading is dropped**
   — `split_sections` only buffers once `current is not None` — so a preamble
   paragraph between the frontmatter and the first section never reaches the
   canonical form and therefore **never moves the hash**; (ii) only `## ` starts a
   section, so `### ` subheadings stay inside their parent section's body and are
   hashed as part of it.
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
     whose content did not change. Pinned by `test_dp_spec_hash.py`.
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

**Stability guard.** The canonicalizer pins `yaml.safe_load` behaviour. A PyYAML
major bump requires re-verifying the golden fixture. WS1 must ship
`evals/tests/test_dp_spec_canonicalization.py` with:
- the golden hash of the worked example in
  `src/nxd-pocket-loop/reference/dp-spec.md`, pinned as a literal.
  **Extraction rule (normative — WS3 edits that file in parallel, so "the worked
  example" must be mechanically identifiable):** the fixture is the content of the
  **sole fenced block whose info string is exactly `markdown`** in
  `src/nxd-pocket-loop/reference/dp-spec.md` — today the fence opening at `:460`
  and closing at `:791`, and the only ```` ```markdown ```` fence in the file
  (every other fence is ```` ```yaml ```` or ```` ```bash ````). The test asserts
  **exactly one** such fence exists and fails loudly if a second appears, rather
  than silently hashing the first. Do not key on line numbers; WS3's edits move
  them;
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

## 4. The closure layout after this change (D1)

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
    ├── contracts/<name>.md    GENERATED (LLM prose) — deferred-model contracts, unchanged
    ├── .gitignore             GENERATED  when a source carries live credentials
    ├── SENSITIVE              GENERATED  when a source carries live credentials
    └── CONTEXT.md             ← DELETED. Does not exist.
```

Nothing under `closure/` is hand-authored. `dp-spec.md` is the only file a user
edits, and it is outside. The pre-approval policy gate keeps its bright line
unchanged — "nothing under `closure/`" — because the byte copy happens **after**
approval, at generation.

### 4.2 Where CONTEXT.md's eight sections went

| CONTEXT.md section | New home |
|---|---|
| 1. Intent | `dp-spec.approved.md` `## intent` |
| 2. Population & sample rule | `dp-spec.approved.md` `## population` + the `decisions` row |
| 3. Per-field inference & determinism caveats | `dp-spec.approved.md` `## models[].fields[].derivation` + `## decisions` (`provenance`) |
| 4. Required-capture fields | **plan half**: new `models[].fields[].required_capture: true` in the spec (WS3). **outcome half** (observed missing rows): `build-record.evidence.required_capture` |
| 5. Derived-model contract for models still to build | `contracts/<name>.md` (unchanged) + new `models[].deferred: true` in the spec (WS3) |
| 6. Reopen recipe | generated `closure/README.md` |
| 7. Credentials | generated `closure/README.md` credentials block; key names come from `sources[].credential_keys` |
| 8. Known blockers | `build-record.blockers[]` |

`closure/README.md` is generated, template-filled, and carries **only** items 6
and 7 — roughly 20 lines. It is not CONTEXT.md under a new name: it has no plan
sections, no outcomes, no rulings, and nothing to hand-copy. Phase C gates its
existence because the reopen recipe is the one thing a cold reader needs that is
neither plan nor outcome.

### 4.3 What Phase C checks instead of CONTEXT.md

Replacing the single `CONTEXT.md exists` check:

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
| C9 | escape scan: no `../…​.md` reference. Scan list becomes `README.md`, `dp-spec.approved.md`, `spec.py`, `models.py`, `transform/main.py`, `contracts/*` | `closure.escaping_reference` |
| C10 | credential guard files — **unchanged** | `closure.gitignore_missing`, `closure.sensitive_missing`, `closure.gitignore_not_naming_profile` |
| C11 | informational: names the `lock verify` command | `closure.canonical_hash_deferred` |

The snapshot **is** scanned by C9. A `../`-rooted markdown reference inside the
approved spec is a real dangling pointer, and the snapshot is where it would
land. No carve-outs are needed anywhere: the escape scan works unchanged because
the IR is *copied* rather than *pointed at*. `dp-spec.lock.json` and
`build-record.json` are JSON and are not in the scan list.

Phase C's success line becomes exactly (frozen string, §9):

```
phase C ok — approved spec snapshot + lock present, no closure-escaping contract references
```

---

## 5. The materialization predicate (D5)

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

The `s0_spec` clause is only satisfiable because `record init` is its producer
(§2.2). Every stage named in this predicate has exactly one writer — `s0_spec`:
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
| `unsettled` | hashes match, offline green, a stage ≥ `s4` failed with no `supervisor_reported` evidence | fail-closed | treat as `code_wrong` |
| `environment_suspect` | hashes match, offline green, every failing diagnostic at stage ≥ `s5` is `owner: environment` **and** `origin: supervisor_reported` per the §1.8.1 relay criterion | the closure is **not** known-bad | **retry** |
| `undisclosed_concession` | otherwise green, some `disclosed: false` | the worst state — reads as materialized | **disclose, then re-evaluate** |
| `awaiting_answer` | otherwise green, `s8_answer` failed | build is green, the answer is wrong | **refine** |
| `in_progress` | any required stage `not_reached` and nothing failed | | continue |

Order of evaluation is the table's order; the first matching state is reported.

**`needs_user` outranks `plan_moved` deliberately.** The two co-occur on the
commonest path there is: a build-time blocker is written back into
`open_questions` (§2.8), which moves the live hash *as a consequence of* the
blocker. If `plan_moved` were reported first the agent would be told to
**regenerate** — against a spec that still carries the unanswered question that
stopped the build. The blocker is both the cause and the only useful next action,
so it is reported first. `why[]` still lists every matching condition, so the hash
divergence is never hidden — only deprioritized.

### 5.2 The label

Call it **`materialized`**. **Never `correct`.** The repo is already blunt about
why: *"SELF-CHECK OK means the closure is structurally sound and the transform
ran, nothing more"* and *"never let a green exit stand in for 'the numbers are
right'"*. `materialized` means the approved plan was compiled, the compiled
artifact ran, and it published. It says nothing about whether the numbers are
right.

---

## 6. The stage ladder and the failure taxonomy (D6, D7)

### 6.1 The ladder

The vocabulary and the offline set are in §1.2. Classify a failure by **which
stage failed**, never by parsing exception text. The stages already differ in
what they have access to; that difference is the classifier.

### 6.2 Stages 0–3 are offline and deterministic

A failure there is **never environmental**. Phase B in particular is the sharpest
instrument in the repo for "a poorly generated DP that won't do its work":
*"Phase B executes for real, so what it reports is what will happen."* A stage-2
failure is unambiguously the code.

### 6.3 The three caveats — written down, not discovered later

1. **Stage 4 masquerades as environment.** Phase A *"cannot execute the
   builders… A closure can pass Phase A in full and still fail when the
   supervisor pins it."* A `build_data_product` failure is **not** presumptive
   evidence of a bad environment. `pin.build_failed` therefore ships with
   `owner: "agent"` in the registry, by construction rather than by evidence.
2. **Phase B covers only `transform/main.py`.** A green Phase B says nothing
   about `spec.py` or `models.py`, and its printed `unverified:` list is its own
   declared blind spot for dynamic constructs. Those lines are emitted as
   `struct.unverified` (`severity: info`) so the blind spot is in the record
   rather than in a scrollback.
3. **Stage 8 failures produce a fully green build.** The distribution read-back
   exists precisely to make them visible — a uniform classification column is the
   tell — and it is non-gating today and stays non-gating. What changes is that
   the build record **records and surfaces** it, adjacent to concessions (§2.6).

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

## 7. The middleman presentation rules (D11)

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

## 8. Elicitation and UI prerequisites (D4)

The spec is an **elicitation contract**: from the user's point of view it
enforces getting enough information to successfully build a DP.
`validate_dp_spec.py` already encodes the conditional requirements — criteria ⇒
verdicts; judgments ⇒ `rubric_version`; every gate ⇒ an `unknown:` rule; every
derived model ⇒ grain + key; every ruling-bearing section ⇒ a `decisions` row.
That is a progressive-disclosure form spec, already written.

**The UI is rendered by the agent harness (e.g. Claude Desktop), not by the
supervisor.** The supervisor cannot do UI. Nothing in this section requires a
supervisor change. What we owe the harness is three things.

### 8.1 (a) Field-addressed diagnostics

Delivered by §1: `{path, code, severity, owner, control, …}` per finding, with
the identity-based path grammar of §1.6 and the per-code `control` hint of §1.5.
The **stable code** matters as much as the path — it is what lets a harness
render an anchors mapping editor for `spec.criteria.incomplete_scale` and a
number field for `spec.criteria.bad_weight`.

### 8.2 (b) A machine-readable schema

```
python3 scripts/dp_diagnostics.py schema --json
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

**The vocabularies are emitted from the Python constants, never re-typed.** To
make that structural rather than aspirational, `REQUIRED_SECTIONS`,
`KNOWN_SECTIONS`, `MODEL_KINDS`, `SOURCE_TYPES`, `DECISION_STATUS`,
`DECISION_PROVENANCE`, `PRODUCED_BY`, `RERUNS`, `DISPOSITIONS` and
`STATUS_VALUES` **move into `scripts/dp_diagnostics.py`**, and
`validate_dp_spec.py` imports them. One definition, two consumers, no drift.

### 8.3 (c) A canonical emitter

Needed for the hash anyway (§3.4); the same component serves form round-trip and
readable diffs.

```
python3 scripts/dp_diagnostics.py canonicalize <spec.md>   # canonical JSON to stdout
python3 scripts/dp_diagnostics.py emit <canonical.json>    # markdown to stdout
```

Law: `canonicalize(emit(canonicalize(x))) == canonicalize(x)`.

**Trap:** the round trip is canonical, not byte-exact — comments, wrapping and
key order are lost. The emitter must therefore **never overwrite a hand-edited
`dp-spec.md` wholesale.** It writes a proposal the user reviews, or a targeted
edit. Silently reformatting the user's own file is the same class of failure as
silently correcting their values.

### 8.4 `provenance` as a rendering property, and the pre-fill trap

`provenance` becomes a rendering property: an agent-filled field renders as
**"proposed, unconfirmed"**, and the user confirming it is real evidence they saw
it. Approval moves `status`; it never moves `provenance`.

**THE TRAP, WRITTEN DOWN EXPLICITLY.** `dp-spec.md` already forbids making the
user re-type into a template: *"Translate it; do not ask them to re-type it."* A
form-first UI regresses to forty empty fields — exactly the failure the IR was
designed to avoid.

> **RULE-PREFILL.** The agent **always** pre-fills from the conversation or the
> user's own document. The UI's job is **review-and-correct, never data entry.**
> A blank form is a fallback, never the entry point. `open_questions` is the only
> surface that should actively demand input.

Mechanization, so this is a rule and not an aspiration: **a blank is illegal in a
rendered form.** A field the agent has no basis for does not appear as an empty
control — it becomes an `open_questions` entry. `validate_dp_spec.py` gains
`spec.prefill.empty_required_field` (`warning`), which fires when a required
field is *present but empty* rather than either filled (with `provenance`) or
carried as an open question.

---

## 9. Frozen strings — the cross-workstream contract

Five agents write these literals into five different files. They must match
exactly. Nothing here may be paraphrased, pluralized or reordered.

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

**New reference files**
`src/nxd-pocket-loop/reference/build-record.md` (WS3)
`src/nxd-generate-dp/reference/closure-record.md` (WS4)
`src/nxd-pocket-loop/reference/failure-handling.md` (WS5)

**Deleted file** — must appear in no `src/` or `docs/` file after integration:
`CONTEXT.md`, `reference/context-doc.md`

**One carve-out, and only one:** `docs/architecture/dp-spec-authoritative.md` —
this note. A design note whose subject is *"`CONTEXT.md` is retired"* cannot
avoid naming it, and it is the historical record of why the file went away.
`test_no_context_doc.py` excludes this path **by exact filename** and nothing
else; the other file under `docs/` (`nexty-pocket.md`, WS3) is in scope and must
be clean. Without the carve-out the test fails on integration against the very
document that specified it.

**The verify-before-build closure file list** — must read identically in
`nxd-generate-dp/SKILL.md` (WS4), `scheduling.md` (WS5),
`handoff-export.md` (WS5), `nxd-review-closure/SKILL.md` (WS5) and the eval
checkers (WS1):

> `spec.py`, `models.py`, `infra-profile.yaml`, `transform/main.py`,
> `requirements.txt`, `dp-spec.approved.md`, `dp-spec.lock.json`,
> `build-record.json`, `README.md`, the connector companion artifact — and,
> for a credentialed source, `SENSITIVE` and `.gitignore`

**`self_check.py` stdout lines** (WS2). Changed:

```
phase C ok — approved spec snapshot + lock present, no closure-escaping contract references
```

Unchanged, and must stay byte-exact — the deterministic-check wiring and the
scenario checkers key on them:

```
phase A ok — …
phase B ok — …
phase D ok — …
SELF-CHECK OK — Phases A (structural), B (transform dry-run), C (context-completeness), D (policy boundary) all passed.
```

**Note the deliberate lie in that literal.** Phase C's *meaning* changes here —
it now verifies the byte-copied spec snapshot, the lock, and the build record,
not a `CONTEXT.md`'s completeness — but its *label* stays
`C (context-completeness)` because the string is byte-exact load-bearing. WS2
MUST leave a comment at the emitting line in `scripts/self_check.py` saying so,
or a later reader will helpfully "fix" the stale label and silently break every
checker that keys on it. Accuracy of the label loses to stability of the
contract; the comment is what keeps that trade visible.

**CLI surface** (WS1), all with `--json` and exit codes `0` ok / `1` findings /
`2` could not read:

```
python3 scripts/dp_diagnostics.py hash        <spec.md>
python3 scripts/dp_diagnostics.py canonicalize <spec.md>
python3 scripts/dp_diagnostics.py emit        <canonical.json>
python3 scripts/dp_diagnostics.py schema      [--json|--diagnostic|--record]
python3 scripts/dp_diagnostics.py lock write  <spec.md> <closure-dir>
python3 scripts/dp_diagnostics.py lock verify <closure-dir> [--spec <spec.md>]
python3 scripts/dp_diagnostics.py record init   --record <path> --lock <path> [--spec-report <report.json>]
python3 scripts/dp_diagnostics.py record append --record <path> --stage <id> --from <report.json>
python3 scripts/dp_diagnostics.py record query  --record <path>
       [--stage …] [--owner …] [--severity …] [--code …] [--unresolved] [--attempt N]
python3 scripts/dp_diagnostics.py materialized --record <path> [--lock <path>] [--spec <path>]
python3 scripts/self_check.py [--json] [--record build-record.json]
```

Style constraint: stdlib-only Python (PyYAML is already a dependency of
`validate_dp_spec.py` and may be used there), `argparse`, `--json`, meaningful
exit codes — consistent with the existing `scripts/`.

**CONSTRAINT-1 (the one that breaks the design if missed).** `self_check.py` is
**copied into the closure and run there**. It can **never** import
`dp_diagnostics.py`. WS2 inlines a minimal literal vocabulary (a `dict` and
`json.dumps`) and WS1 ships `evals/tests/test_self_check_diagnostic_vocab.py`
asserting that every code and stage literal in `scripts/self_check.py` exists in
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

## 10. File-by-file change manifest

Five workstreams, disjoint file ownership. **No file appears in two
workstreams.** All five may proceed in parallel against §9's frozen strings.

### WS1 — diagnostics core, the validator, and all of `evals/`

**Owns:** `scripts/validate_dp_spec.py`; `scripts/dp_diagnostics.py` (NEW);
everything under `evals/` **except** `evals/tests/test_self_check_sync.py` and
`evals/tests/test_policy_boundary_phase_d.py` (WS2).

The blanket `evals/` ownership includes `evals/private/`, which was checked and
holds only a `README` with no `CONTEXT.md` references — so nothing customer-specific
is in scope and the AGENTS.md safety rule ("private evals stay under
`evals/private/`; nothing customer-specific in public evals") is unaffected.

| File | Edit |
|---|---|
| `scripts/dp_diagnostics.py` **NEW** | The shared module. `Diagnostic` dataclass; `CODES` registry (§1.5, complete); `DIAGNOSTIC_SCHEMA`, `BUILD_RECORD_SCHEMA`, `LOCK_SCHEMA`; the spec vocabularies moved out of `validate_dp_spec.py` (§8.2); `canonicalize()` / `spec_hash()` / `emit()` (§3.4, §8.3); the lock writer/verifier (§3.2, §3.5); the `BuildRecord` reader/writer with INVARIANT-D2 enforcement (§2.5); `materialized()` (§5); the redaction pass (§1.7); the full CLI (§9). |
| `scripts/validate_dp_spec.py` | Import vocabularies from `dp_diagnostics`. Replace `Report.errors/warnings: list[str]` with `list[Diagnostic]`; every `report.error(...)` / `report.warn(...)` call site takes a `code` + identity-based `path` per §1.5/§1.6 — one code per existing check, no check dropped, **verified by `test_validator_code_coverage.py` in both directions** (§1.5.1). Mind the two many-to-one codes and their `evidence.reason` enums (§1.5.1 (i)). `--json` emits `nxd-diagnostic-report-v1` with `tool: "validate_dp_spec"` and `spec_hash`. Human output keeps `WARN`/`ERROR` lines but prefixes the code. Add `spec.prefill.empty_required_field` (§8.4). Exit codes unchanged. |
| `evals/public/coauthor-supplied-rubric/fixtures/check_coauthored_closure.py:38-46` | **BREAKS (hard).** `REQUIRED` tuple: drop `"CONTEXT.md"`, add `"dp-spec.approved.md"`, `"dp-spec.lock.json"`, `"build-record.json"`, `"README.md"`. |
| `evals/public/coauthor-executable-policy-readback/fixtures/check_executable_policy.py:44-52` | **BREAKS (hard).** Same `REQUIRED` edit. Do not touch its ordering output — `test_executable_policy_gate.py`'s 30 tests grade that and are otherwise safe. |
| `evals/tests/test_generation_subagent_gate.py:194-200` | **BREAKS (hard).** Assert the §9 verify-before-build list against `scheduling.md` instead of `"CONTEXT.md"`. |
| `evals/tests/test_resume_first_gate.py:32,104-116` | **BREAKS (hard, `FileNotFoundError`).** Repoint `GENERATE_DP_CONTEXT_DOC` from `reference/context-doc.md` to `src/nxd-generate-dp/reference/closure-record.md` (WS4's new file, §9). |
| `evals/public/country-income-trajectory/checks.json:22,38,46,66` | **BREAKS (soft).** "an `nxd_decisions` row or a CONTEXT.md statement" → "an `nxd_decisions` row or a `dp-spec.approved.md` `decisions:` entry"; the file-set enumeration at :66 → §9 list. |
| `evals/public/worldbank-live/checks.json:71` | **BREAKS (soft).** "FAIL if CONTEXT.md is missing" → the snapshot disclosure now lives in `dp-spec.approved.md` `## sources.scope` / `## population.excludes`; FAIL if `dp-spec.approved.md` or `build-record.json` is missing. |
| `evals/public/treasury-yield-curve/checks.json:72` | **BREAKS (soft).** File-set enumeration → §9 list. |
| `evals/public/coauthor-executable-policy-readback/checks.json:67` | **BREAKS (soft).** "not in CONTEXT.md's description" → "not in `dp-spec.approved.md`". |
| `evals/public/pocket-loop-export-handoff/fixtures/check_pocket_loop.py:50-55` | **BREAKS (soft).** CONTEXT.md soft-signal comment/set → the new soft set. |
| `.../coauthor-supplied-rubric/prompt.md:44`, `.../coauthor-executable-policy-readback/prompt.md:96`, `.../pocket-loop-export-handoff/prompt.md:19` | **BREAKS (silent).** Prompts that tell the agent to emit `CONTEXT.md` would keep producing it. Remove the instruction. |
| `evals/tests/test_dp_diagnostics_schema.py` **NEW** | JSON Schemas are valid; every registry code has stage/severity/owner/control; no duplicates; the code list is pinned as a frozen snapshot (a rename fails the test). Also pins the closed `tool` enum of §1.8 (`validate_dp_spec` · `self_check` · `dp_diagnostics` · `loop`) and the stages each value may carry. |
| `evals/tests/test_validator_code_coverage.py` **NEW** | §1.5.1 (iii). AST-walks `scripts/validate_dp_spec.py`: every `report.error(` / `report.warn(` call site passes `code=`; every such literal is in `CODES` with `stage == "s0_spec"`; **and** every `spec.*` code in `CODES` is emitted by ≥1 call site. This is what keeps "one code per existing check, no check dropped" true by construction rather than by review. |
| `evals/tests/test_build_record_s0_producer.py` **NEW** | `record init` fills `stages.s0_spec` (never `not_reached` on a fresh record); it validates the **snapshot**, not the live IR; `--spec-report` with a `spec_hash` ≠ `lock.spec_hash` exits 2; `record append --stage s0_spec` is rejected (§2.2). |
| `evals/tests/test_dp_spec_canonicalization.py` **NEW** | The §3.4 golden hash + must-not-change / must-change tables + the idempotence law. |
| `evals/tests/test_build_record_schema.py` **NEW** | A golden record validates; the §5.1 state machine as a truth table; INVARIANT-D2 rejection. **Plus the §2.5 ORDERING RULE, both directions**: a `kind: "heal"`, `exit: "blocked"` attempt with equal hashes alongside a `blockers[]` entry with `written_back: true` is **accepted** and must NOT emit `blocker.spec_edit_required` (the false-accusation case); the same attempt with differing hashes **is** rejected. And the `plan_moved` / `spec_edit_required` disjointness: a live-hash divergence reaches §5.1 only as `plan_moved`. |
| `evals/tests/test_self_check_diagnostic_vocab.py` **NEW** | CONSTRAINT-1: `self_check.py`'s inlined codes/stages ⊆ `dp_diagnostics.CODES`. |
| `evals/tests/test_closure_layout_gate.py` **NEW** | The §9 verify-before-build list appears identically in all four skill files. |
| `evals/tests/test_no_context_doc.py` **NEW** | `CONTEXT.md` and `context-doc.md` appear nowhere under `src/` or `docs/`, with the single exact-filename carve-out for `docs/architecture/dp-spec-authoritative.md` (§9). **Ships `@pytest.mark.skip`**; the coordinator un-skips at integration (it fails until all five land). |

Also **verify (may not need edits)**: `test_deterministic_check.py`,
`test_deterministic_check_wiring.py`, `test_write_markers_match_emitter.py`,
`test_export_public_classification_gate.py`, `test_desktop_install_layout.py`.
`test_static_artifact_lifecycle_gate.py` and `test_executable_policy_gate.py`
were checked and are **not** broken.

### WS2 — `self_check.py` and its byte-identical twin

**Owns:** `scripts/self_check.py`, `src/nxd-generate-dp/reference/self-check.md`,
`evals/tests/test_self_check_sync.py`, `evals/tests/test_policy_boundary_phase_d.py`.

These four move as **one atomic commit** — `test_self_check_sync.py` requires the
script and the fence to be byte-identical, and `test_policy_boundary_phase_d.py`
slices the fence by literal string.

| Change | Detail |
|---|---|
| Diagnostic buffering | Accumulate `nxd-diagnostic-v1` dicts alongside the existing prose. Inline vocabulary — **never import `dp_diagnostics`** (CONSTRAINT-1). |
| `--json` | Detected by `"--json" in sys.argv` (no argparse — keep the script small and its twin simple). Emits one `nxd-diagnostic-report-v1` object to stdout. Default output is **unchanged prose** (CONSTRAINT-2). |
| `--record <path>` | Merges `s1_structure`, `s2_transform`, `s3_closure` into `build-record.json` in place. Default off. |
| Early exit / `not_reached` | Keep exiting on the first failing phase (Phase B cannot run over malformed code), but with `--json` emit the report **before** exiting, with later stages `status: "not_reached"` and a `meta.stage_not_reached` diagnostic. |
| **Phase C rewrite** | Delete the `CONTEXT.md` existence check. Implement C1–C11 (§4.3). New scan list for C9: `README.md`, `dp-spec.approved.md`, `spec.py`, `models.py`, `transform/main.py`, `contracts/*`. Success line = the §9 frozen string. Credential-guard block unchanged. |
| Phase A | Emit `struct.unverified` (`info`) per `unverified:` line. Behaviour otherwise unchanged. |
| Phase B | Emit `runtime.row_count` (`info`) per model instead of only printing. |
| Phase D | **Do not restructure.** Keep `derrors = []` and `if derrors:` as literals and keep the phase in place (CONSTRAINT-3). Add codes only. |
| Read-back | Emit `semantic.distribution` / `semantic.uniform_column` / `semantic.absent_vocabulary`; keep printing the prose lines unchanged. |
| `self-check.md` prose | Update the Phase C description, the phase table, and the `CONTEXT.md` references to the snapshot/lock/record model. **One** `# self_check.py` fence, still the longest (CONSTRAINT-3). |

### WS3 — the IR reference and the build-record reference

**Owns:** `src/nxd-pocket-loop/reference/dp-spec.md`,
`src/nxd-pocket-loop/reference/build-record.md` (NEW),
`docs/architecture/nexty-pocket.md`.

| File | Edit |
|---|---|
| `reference/dp-spec.md:45-48` | Delete "It is **not** a replacement for `CONTEXT.md`…". Replace with the snapshot/lock model: the IR stays beside; the approved spec is byte-copied in at generation. |
| `reference/dp-spec.md:50-76` | Rewrite "Where it lives, and why not in the closure": keep both original reasons, add that self-containment is now a hash-checkable snapshot rather than prose discipline, and that Phase C's escape scan needs no carve-outs. Update the tree to §4.1. |
| `reference/dp-spec.md:371-391` | "What each section compiles to" — drop the three `CONTEXT.md` cells; add rows for `dp-spec.approved.md` and the lock. Keep the table framed as a **review aid, not a rebuild graph** (D3: the fan-in is many-to-many, not a DAG). |
| `reference/dp-spec.md` `## models` | **New optional model-entry keys**: `deferred: true` (contract carried in `contracts/<name>.md`, not `.promise`d) and `fields[].required_capture: true` (§4.2 rows 4 and 5). Document both; WS1 adds validation. |
| `reference/dp-spec.md:393-432` | "The validator" — document the new `--json` envelope, the code registry, and the field-addressed path grammar (§1.6). |
| `reference/dp-spec.md:434-446` | "Approval" — add that approval is what gets byte-copied and hashed; that the hash mechanizes "once approved, the spec is frozen for that build" (previously honour-system); and that a build-time blocker written back into `open_questions` **un-approves** the spec. |
| `reference/dp-spec.md` worked example | **Do not change a byte** unless you also update WS1's golden hash. If the example must change, coordinate. |
| `reference/build-record.md` **NEW** | The normative reader-facing doc for §1, §2, §5, §6. Opens with `## Contents` (over 100 lines). Covers: the unified diagnostic record; the build record schema field by field; origins; attempts and the caps; the concession split; the stage ladder and the three caveats; the fail-closed rule; the materialization predicate and its states; the `dp_diagnostics.py` CLI. |
| `docs/architecture/nexty-pocket.md:8,44,76,86-133,150,282-284` | Delete the "Context capture: `CONTEXT.md` and `nxd_decisions`" section; replace with "Spec snapshot, lock and build record", linking here. Update the closure diagram (:44), the skill table (:76), the Phase C row of the self-check table (:150), and the known-gaps note at :282-284 (the CONTEXT/`nxd_decisions` drift gap is **closed** — the ledger is now a projection of a hashed snapshot). |

### WS4 — the generator skill

**Owns:** `src/nxd-generate-dp/SKILL.md`;
`src/nxd-generate-dp/reference/context-doc.md` (**DELETE**);
`src/nxd-generate-dp/reference/closure-record.md` (NEW);
and the four remaining `nxd-generate-dp/reference/` files that mention
`CONTEXT.md` or link to `context-doc.md`: `adversarial-review.md`,
`database-source.md`, `policy-gate.md`, `derived-models.md`.

Those four were previously owned by nobody, which would have failed integration:
§9 freezes `CONTEXT.md` and `context-doc.md` as strings that **must appear in no
`src/` or `docs/` file**, WS1's `test_no_context_doc.py` enforces exactly that
when the coordinator un-skips it, and `derived-models.md:379` additionally links
to a file WS4 deletes — a dangling link the moment WS4 lands. They sit under
`nxd-generate-dp/reference/` and no other workstream touches them, so adding them
here preserves the disjoint-ownership rule.

**LINE BUDGET — binding, same as WS5's.** `src/nxd-generate-dp/SKILL.md` is
**499 lines today** and `validate_skills.py` fails at 501, so WS4 has **one line
of headroom**. Step 6a's rewrite and the D2/D7 rules below are net-additive, so
the "push detail into `closure-record.md` and leave a pointer" instruction in the
table is **not a stylistic preference — it is the only way this workstream
passes CI.** Budget the detail out before writing it in, and re-check
`wc -l src/nxd-generate-dp/SKILL.md` before returning.

| File | Edit |
|---|---|
| `reference/context-doc.md` | **DELETE.** Its `contracts/<name>.md` template moves to `closure-record.md` — do not lose it. |
| `reference/closure-record.md` **NEW** | How the generator emits the record surfaces, at ~120 lines with a `## Contents`: the byte-copy procedure; `prompt_ref` mirroring (§3.6); writing the lock; `record init`; the `README.md` template (reopen recipe + credentials block **only** — §4.2); the `contracts/<name>.md` template carried over verbatim. Normative schema lives in WS3's `build-record.md`; **link, do not restate**. |
| `SKILL.md:64` | Closure-layout comment: `CONTEXT.md` → the four generated record files. |
| `SKILL.md:117` | "what a later session needs is copied into `CONTEXT.md`" → "the approved spec is byte-copied in as `dp-spec.approved.md` under a lock". |
| `SKILL.md:413-439` | **Rewrite Step 6a.** Was "`CONTEXT.md`: the in-closure design/process record". Becomes "Snapshot the approved spec and open the build record": copy `dp-spec.md` → `dp-spec.approved.md` byte-for-byte; mirror `prompt_ref` files; `dp_diagnostics.py lock write`; `record init`; render `README.md`. Point at `reference/closure-record.md`. Keep the paragraph that the record does not replace machine-enforced surfaces (`nxd_decisions` + Step-3b asserts still run). |
| `SKILL.md:441-473` | **Step 7.** Now runs `python3 self_check.py --json --record build-record.json` **and** `python3 scripts/dp_diagnostics.py lock verify <closure>` (§3.5). Update the Phase C description at :456. In the Step 6b adversarial-review paragraph at :443, "record the round in `CONTEXT.md`" → "record the round in `build-record.json` `attempts[]`". |
| `reference/adversarial-review.md:83-84` | "Record the round in `CONTEXT.md`: each finding's `id`, its adjudication, …" → record the round in `build-record.json` `attempts[]` (`kind: "heal"` for an accepted finding that changed code; the adjudication and its citation go in `diagnosis.summary` / `changed[].what`). Keep the paragraph that follows verbatim — "rulings are landed as reviewable data rather than buried in prose" is *more* true after this change, not less. Must match WS4's own edit to `SKILL.md:443`. |
| `reference/database-source.md:156` | Never-write-a-credential-value list: `` `SENSITIVE`, `CONTEXT.md`, `README.md`, or chat narration `` → `` `SENSITIVE`, `README.md`, `dp-spec.approved.md`, `dp-spec.lock.json`, `build-record.json`, or chat narration ``. The rule is unchanged and now covers the generated record files; §1.7's mandatory redaction pass is the mechanical half of the same rule. |
| `reference/policy-gate.md:108` | "carry the approved text verbatim into `CONTEXT.md` and `nxd_decisions`" → "the approved text is carried verbatim by the byte-copied `dp-spec.approved.md`, and lands as data in `nxd_decisions`". The gate itself is untouched — this is the one place the *approved* text was previously hand-copied, and the byte copy is now what carries it. Do not weaken "surface the encoded bands in your return". |
| `reference/derived-models.md:379` | Dangling link: `[context-doc.md](context-doc.md)` → `[closure-record.md](closure-record.md)`, and reword to point at where `required_capture` now lives — the **plan** half is `models[].fields[].required_capture: true` in the spec (WS3), the **outcome** half is `build-record.evidence.required_capture` (§4.2 row 4). The `listed_uncaptured` / genuinely-absent distinction below it is unchanged. |
| `SKILL.md:474-490` | **Invariants.** :476 file list → §9. :477 rewrite the self-containment invariant around the snapshot+lock. :478 sample-selection: the rule is stated in the **spec**; observed missing required-capture rows go to `build-record.evidence.required_capture`. :485 delete "what a later session needs is copied into `CONTEXT.md`"; **add the D2 hard rule**: the self-heal loop may change generated code and never the IR; if green is only reachable by changing the plan, stop and escalate `blocker.spec_edit_required`. **Add the forbidden/discouraged split (§6.6)** naming the four existing absolutes as `blocker.forbidden_*`. |

SKILL.md must stay under 500 lines; it is at 500-ish today, so push detail into
`closure-record.md`.

### WS5 — the loop skill and the reviewer

**Owns:** `src/nxd-pocket-loop/SKILL.md`,
`src/nxd-pocket-loop/reference/scheduling.md`,
`src/nxd-pocket-loop/reference/handoff-export.md`,
`src/nxd-pocket-loop/reference/context-and-resume.md`,
`src/nxd-pocket-loop/reference/failure-handling.md` (NEW),
`src/nxd-review-closure/SKILL.md`.

**LINE BUDGET — read this before writing a line.** `src/nxd-pocket-loop/SKILL.md`
is **exactly 500 lines today**, and `validate_skills.py` fails at 501
(`line_count > max_lines`, default 500). WS5's edits are net-additive — R1–R8, the
typed exits, the stage-4 caveats, the countable caps — and WS3 owns
`reference/build-record.md`, so WS5 had no file to absorb them. It has one now:
**`reference/failure-handling.md` (NEW, WS5-owned)**. Push the detail there and
leave pointers in `SKILL.md`; several of the edits below are net-*negative* on
line count if done that way. Check with `wc -l src/nxd-pocket-loop/SKILL.md`
before handing off — a 501-line SKILL.md fails CI for every other workstream too.

| File | Edit |
|---|---|
| `pocket-loop/SKILL.md:79-87` | The six-tool sentence names `inspect_run` and nothing else in the pack ever uses it. State plainly that it is **unbound**: no reference doc, no step calls it, and the build record marks supervisor-side detail `origin: unbound` until a producer exists. Do not invent a contract for it. |
| `pocket-loop/SKILL.md:163-205` (Step 1b) | Add: approval is what gets snapshotted and hashed; a build-time blocker is written back into `## open_questions`, which **un-approves** the spec and re-enters this step. The elicitation contract is a loop. |
| `pocket-loop/SKILL.md:215-269` (Step 3) | Closure file list → §9. Relay rule for the distribution read-back: it is now recorded in `build-record.readback`, still relayed verbatim, still non-gating. |
| `pocket-loop/SKILL.md:220,259-262` | Replace the `CONTEXT.md` durable-record sentences with the snapshot/lock/record trio. Keep "`../dp-spec.md` included" as the escaping-pointer example — it is still exactly right. |
| `reference/failure-handling.md` **NEW** | WS5's headroom file, ~120 lines, opens with `## Contents`. Carries the detail the three rows below would otherwise inline: the stage ladder as the loop sees it and the three caveats (§6.3); fail-closed classification and its discriminating test (§6.4); the typed heal exits and the countable caps (§6.7, §2.10); the narration rules R1–R8 and the banned vocabulary (§7). Normative schema stays in WS3's `build-record.md` — **link, do not restate**; this file is the loop's operating procedure over it. |
| `pocket-loop/SKILL.md:270-300` (Steps 4/4a) | On a build failure: **stage-4 masquerades as environment** (§6.3 caveat 1); classify fail-closed (§6.4); record the attempt. Do not report an environment cause without supervisor-reported evidence. Two or three lines plus a pointer to `reference/failure-handling.md`. |
| `pocket-loop/SKILL.md:345-366` (Step 6) | Caps are now **counted** from `build-record.attempts[]`, not estimated. Name the typed heal exits (§6.7); their definitions live in `reference/failure-handling.md`. |
| `pocket-loop/SKILL.md:367-382` | **Narration discipline** — R1 (two classes only), R2 (`owner`, not `severity`, decides) and R5 (never present green as right) belong here in the SKILL; R3–R4 and R6–R8 with their worked examples go to `reference/failure-handling.md`. This is where D11 belongs, but it does not all fit here. |
| `pocket-loop/SKILL.md:383-483` | Invariants: the D2 hard rule (heal changes code, never the IR); no green claim while an undisclosed concession stands; `materialized`, never `correct`. |
| `pocket-loop/SKILL.md:493-500` | Add `reference/build-record.md` (WS3's) **and** `reference/failure-handling.md` to the reference-docs list. |
| `reference/scheduling.md:73-84` | Caps become countable; name `build-record.attempts[]` and `caps`. |
| `reference/scheduling.md:130` | Subagent context list: `CONTEXT.md` → the generated record files. |
| `reference/scheduling.md:198-215` | **Verify-before-build list → §9 verbatim** (WS1's `test_generation_subagent_gate.py` asserts against this exact text). |
| `reference/handoff-export.md:87` | "the `CONTEXT.md` inside the closure carries the full contract" → `dp-spec.approved.md` carries the approved plan; `build-record.json` carries what happened. |
| `reference/handoff-export.md:121` | Zip contents list → §9 list. |
| `reference/context-and-resume.md:25` | Durable-key bullet: `CONTEXT.md` → `dp-spec.approved.md` + `dp-spec.lock.json` + `build-record.json` + `README.md`. |
| `reference/context-and-resume.md:29-35` | "**`CONTEXT.md`** and **`nxd_decisions`**" → "the **approved spec snapshot** and **`nxd_decisions`**". Keep the two-axis `status`/`provenance` paragraph verbatim — it is unaffected and still correct. |
| `review-closure/SKILL.md:25` | Given-files list → §9. |
| `review-closure/SKILL.md:50` | "The closure, or its `CONTEXT.md`, states or implies…" → "The closure, or its `dp-spec.approved.md`, …". |
| `review-closure/SKILL.md:92-96` | **The dangling deferral.** "`CONTEXT.md` section completeness" defers to a check that does not exist. Replace with the checks that now **do** exist: snapshot present, lock present and byte-matching, `build-record.json` present with `compiled_from` matching. Add: the reviewer confirms **both** Step-7 commands ran (`self_check.py` and `lock verify`, §3.5). |

### Serialized integration step (coordinator, not a workstream)

Performed **after** all five land, as one commit, because it touches files owned
by several workstreams:

1. Bump `.claude-plugin/plugin.json` `version` `0.27.0` → **`0.28.0`** (minor:
   added capability), mirror into `.claude-plugin/marketplace.json`, and set
   `metadata.version: 0.28.0` in **every** `src/*/SKILL.md` (AGENTS.md version
   lockstep).
2. Un-skip the four cross-workstream tests. **Every test that asserts against a
   file another workstream owns MUST ship `@pytest.mark.skip(reason="un-skip at
   integration — asserts against WS<n>-owned files")`**, because it cannot pass
   until that workstream lands and a red suite mid-fan-out is indistinguishable
   from a real regression. That is all four, not just the obvious one:
   `test_no_context_doc.py` (new), `test_closure_layout_gate.py` (new — asserts
   §9 text in four WS4/WS5 files), `test_resume_first_gate.py` (edited —
   repointed at WS4's `closure-record.md`), `test_generation_subagent_gate.py`
   (edited — asserts the §9 list in WS5's `scheduling.md`).
3. `python3 scripts/validate_skills.py --root .`, `./build-skills.sh`
   (200-entry cap — the new reference files and deleted `context-doc.md` change
   the counts), **and `python3 -m pytest evals/tests/ -q`**. All three, and the
   pytest run happens *after* step 2 — the un-skip is what makes it meaningful.
   Report the real output; a suite that was never run is not a green suite.
4. Benchmark: this changes skill behaviour, so run the affected scenarios before
   and after and record with `evals/benchmark_record.py` into
   `evals/benchmarks/ledger.md` (AGENTS.md). Affected scenarios:
   `coauthor-supplied-rubric`, `coauthor-executable-policy-readback`,
   `pocket-loop-export-handoff`, `country-income-trajectory`, `worldbank-live`,
   `treasury-yield-curve`.

No changes are needed to `evals/skill-sets.yaml` or the README **Available
Skills** table — no skill directory is added or removed.

---

## 11. What we are explicitly NOT doing

- **No per-section hashing.** Considered and rejected. The "what each section
  compiles to" table is **many-to-many fan-in, not a DAG** — `nxd_decisions` is
  fed by population, gates, criteria, verdicts and open questions; a criteria
  change cascades through `rubric_version` into judgments. With an LLM doing
  codegen, partial regeneration also risks breaking the `PHYSICAL_MODELS` naming
  invariant, which spans `models.py`, `spec.py` and the transform. **One
  whole-spec hash.** The table stays a review aid, never a rebuild graph.
- **No supervisor changes.** Everything here is in-repo. Stage-4 detail,
  per-attempt identity and the supervisor traceback are **schema without a
  producer** (`origin: "unbound"`). `mcp__nxd-desktop__inspect_run` is a name in
  one sentence of one skill file and nothing else in the pack — no schema, no
  reference doc, no step, no test. Do not design around a guess about what it
  returns.
- **The live IR does not move into the closure.** It stays beside. The
  pre-approval policy gate keeps its bright line ("nothing under `closure/`"),
  drafting history and rejected options stay out of handoffs, and the byte copy
  happens after approval.
- **No `materialized` status value on the spec.** `status` stays
  `draft | proposed | approved`. Materialization is a **derived predicate** over
  the lock and the build record (§5). Putting it in the spec would put an outcome
  back into the IR.
- **No new gate on the distribution read-back.** It stays non-gating. What
  changes is that it is recorded as data and surfaced next to concessions.
- **No merging of source-data staleness into materialization.** `transform_state`
  freshness is a separate axis, recorded in `evidence.source_state` and excluded
  from the predicate.
- **No UI in this repo.** We ship the three prerequisites the harness needs
  (field-addressed diagnostics, the machine-readable schema, the canonical
  emitter) and nothing that renders.
- **No `errors[]`/`warnings[]` compatibility shim** in `validate_dp_spec.py
  --json`. Nothing reads it; carrying both shapes invites drift.

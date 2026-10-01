# dp-scenarios — multi-turn data-product scenario suite

This suite measures whether an agent can build a correct data product while a
human keeps changing the conversation. It runs scenarios the way a BI analyst
actually works — a vague first message, corrections mid-stream, disputes after
the fact — and grades the result mechanically, never by trusting the agent's own
account of what it did.

Isolated uv project (mirrors `evals/nxd_eval/` and `evals/mcp/`). Everything runs
via `uv run --project evals/dp-scenarios …` — never bare `python`/`pip`.

## How it works

A **scenario** is a scripted conversation with a hidden answer key.

1. The **operator** — the harness playing the human — sends the opening ask. It
   is deliberately vague, the way a real request is.
2. The **agent under test** replies and works: reading sources, writing a spec,
   building the product, querying it. It uses the real Nextdata skills against a
   real runtime, not a simulation.
3. The operator answers follow-up questions from an **answer sheet**, and at
   scripted moments injects **events** — a scope change, a redefinition, a
   restart — to see whether the agent adapts or quietly carries on.
4. When the script is exhausted, the harness grades what was actually produced.

The whole point is step 4. The agent's summary of its own work is evidence of
nothing, so grading reads the artifacts: the built tables, the query results, the
governed decisions, the ledger of what happened each turn.

### How it grades

Grading is **model-free and deterministic**. There is no judge model anywhere in
the grading path, because a verdict that depends on a second provider's
availability and version is not a verdict you can trust over time.

Each scenario is scored by **gates**, each answering one question about the
evidence:

| Gate | Asks |
|---|---|
| `intake` | Did the agent get an approved definition before writing code? |
| `capability` | Did it govern what the source cannot actually answer? |
| `narrowing` | Did the definition change when the operator changed it? |
| `construction` | Did it self-check and adversarially review its own work? |
| `build` | Did a release publish, carrying the supervisor's own `run_id`, `artifact_id` and `publish_sequence`? Row counts are not compared here — the fixture oracle counts source tables and the supervisor counts built models, which no modelling choice makes equal; ledger lint checks the agent's claimed counts against the supervisor's. |
| `query` | Do the answers match the fixture's ground truth? |
| `follow-up` | The scenario's own specific drill. |

A gate can **pass**, **fail**, or be **not examined**. That third state matters:
it means the evidence to judge it never appeared, which is not the same as
passing. A gate that cannot fail is worse than no gate, so gates are written to
report not-examined rather than quietly return a clean result.

Beyond the gates, several **hard checks** can invalidate a run outright: a
planted secret appearing where it should not (`sentinel`), the agent reading the
answer key (`gold_access`), the ledger failing its lint, or traffic that never
reached the mock source it claimed to read (`route_fidelity`).

### What a result is worth

A passing run is not automatically trustworthy, so every run also carries a
**qualification** recording what its evidence actually supports:

| Disposition | Meaning |
|---|---|
| `CERTIFIED` | Clean, replay-verified, and repeated across the epochs the scenario demands |
| `QUALIFIED` | Clean, but something caps it — a model authored the operator's words, for instance |
| `OBSERVED` | Something was seen, but the run cannot support a claim: a turn timed out, or it was replay-only |
| `REJECTED` | Graded and failed |
| `INVALID` | The environment broke; the run says nothing about the agent |

A run that stopped early can never be reported clean, because the gates it did
reach are not evidence about the ones it never got to.

#### Engine terminal states

| State | Meaning |
|---|---|
| `completed` | The scripted interaction ended with a clean terminal result. |
| `turn_budget_exhausted_pending_answer` | The turn budget ended while an operator answer or review choice was still owed. |
| `approval_budget_exhausted` | The agent asked for approval after exhausting a workflow's two revision reapprovals. The run is incomplete and remains ungraded. |
| `script_exhausted` | The operator script ended without proving completion, or an applicable operator answer or fixed beat remains owed. |
| `chain_prefix_failed` | A chained scenario's prefix failed, so its suffix could not run. |
| `sentinel_trip` | A protected sentinel was observed in agent output. |
| `environment_wedge` | The run's environment failed before the scenario could be judged. |
| `turn_timeout` | A provider turn exceeded its time limit. |

## Operator modes

The operator is the harness playing the human. It has three modes, and the mode
is recorded per turn in the evidence.

**Scripted** (default). A keyword matcher picks a canned reply from the answer
sheet. Fully deterministic and replayable — the same run can be re-executed and
verified turn for turn. This is the only mode that can reach `CERTIFIED`.

**Generated surface.** The scripted reply is rephrased by a model, so the agent
does not see the same sentence twice, but the *substance* is still the harness's.

**Driver** (`--driver-model`). A model authors the words of each substitutable
turn from a persona and a ground-truth brief, so the agent faces someone who
reacts rather than an answer bank. The engine still owns everything that decides
what the run means: phase map, turn budget, event injection, ledger rows,
terminal state. The driver only chooses how the persona says things.

Three kinds of turn are never authored: the first, any turn the script marks
non-substitutable, and any approval turn — an approval must transmit its declared
line verbatim, because that text becomes the approval of record.

Because a model wrote the operator's words, a driven run cannot be replayed
turn-for-turn and is **capped at QUALIFIED**. Use the driver to observe persona
behaviour a scripted operator cannot produce, not to certify a result.

Event cards normally fire on their declared `trigger_turn`. A card may instead
declare `after_published: initial|revised` and/or `after_event: <id>`; its
`trigger_turn` is then the earliest turn it may fire. Publication prerequisites
use the runner-owned `run-records.status_history` observed before the current
turn, cross-checked against an exact workflow/run/definition entry in
`publication-history.json`. The release record's `turn` is the run start and is
never used as the publish observation. An `after_event` prerequisite uses the
turn when that card was actually delivered. Fixed cards due on a turn take
precedence, and eligible publication cards are delivered one per turn in stable
card order. Replays carry only the bounded runner-owned identities and status
history needed to make the same scheduling decision.

Two properties a free-authoring operator could destroy are checked mechanically
before any authored message is sent:

- **Leading.** A model told it is an analyst who knows the business will
  volunteer the join key or the grain — destroying a scenario whose whole point
  is that the agent discovers them. Every authored message is scanned for the
  scenario's `driver_forbidden_terms`. Terms the agent already used itself are
  exempt, so the operator can answer in the agent's own words.
- **Dropped beats.** A driver that declines to carry a scripted event leaves the
  scenario grading nothing while looking like a clean run, so the message is
  checked for the beat and the engine's own delivery predicate gets the last
  word.

Either violation is named back to the model, which authors once more; a second
failure sends the scripted line instead. **A rejected call is a fallback, not an
abort** — the run completes and spends the full agent budget either way — so the
summary states per epoch whether the driver authored every substitutable turn or
fell back.

## Scenarios

Scenarios are selected by the `tier` each one declares. `smoke`, `core`, and
`full` packages grade replayable supplied evidence; `live` packages grade a
live agent session and cannot be replayed.

**Smoke** runs on every skill, runtime, or generator change, takes minutes, and
spends nearly nothing on models. It runs in `run_order`:

1. **drift-canary.** A frozen kitchen-sink closure exercising every surface the
   installed skill texts claim to support. A DRIFT verdict **gates the tier**:
   running the rest against known guidance-vs-runtime drift just re-measures the
   canary's finding at higher cost.
2. **zero-row-optional-output.** A valid resource that materializes no rows.
   Manufacturing a placeholder row fails; so does relaxing the checks that still
   guard required outputs.
3. **parent-child-grain-trap.** Seeded parent/child data where a naive join fans
   the parent amount out across children. Reconciliation is against a fixture
   control total, because self-consistent wrong numbers agree with each other.

**Core** needs heavier infrastructure (one requires a Docker Postgres) and is
never pulled into a smoke run:

- **credential-rotation** — a disposable owned Postgres with a command-stepped
  rotation, graded on connection-level evidence rather than the fixture's
  narrative.
- **sigterm-diagnosis** — the graded difficulty is the *diagnosis*, not the
  failure. The naive plan is SIGTERM-killed with no staging marker, and the
  attribution must land on the supervisor transform window rather than memory, an
  RPC deadline, or a code bug. The overrun is guaranteed by construction, never
  by row counts.
- **restart-and-switch** — an attempt-keyed, no-stderr bind fault paired with a
  scripted restart and workflow switch. The agent must distinguish serving-down
  from build-broken and change the plan rather than retry until lucky.
- **crm-pipeline** — B1's paginated CRM-shaped source with bearer expiry,
  rate limiting, nested owner PII, tombstone-safe current records, and a closed
  stage enum. The package has local mock-source E2E coverage; it does not claim
  a real CRM credential or authenticated agent run.
- **crm-pipeline-drift** — B11's chained refresh of B1's CRM source. The first
  publication switches the local route to a drifted source; the agent must
  obtain a new business ruling and publish a separate reviewed workflow.
- **finance-close** — B2's deterministic close reconciliation with hostile
  decimal formats, parenthesized negatives, missing weekend FX, and a later
  decision supersession. It exposes a local mock close source and reconciles
  exact cents against an independent reference model.
- **inventory-position** — B5's profile-only inventory join with orphan
  warehouse identifiers and negative stock. The local mock profile preserves
  these as data-quality warnings and documents the retained-run boundary for
  B10.
- **application-reconciliation** — C2's 391-row export versus 353-row active
  dashboard dispute, with 30 status exclusions and 8 tombstones reconciled by
  independent lineage evidence.
- **locale-timezone** — C6's UTF-8 categories, real America/New_York DST
  transition, and UTC date-boundary event, where source-local and UTC daily
  views preserve totals while one of 14 rows shifts.

**Full** covers deterministic cross-source decisions that are too specific for
the routine core suite:

- **marketing-attribution** — B3's safe campaign-name matching, including
  case/whitespace normalization, one unique 50-character truncation, and a
  matched-conversions-only CPA policy, with a leak scan over an unrelated newsletter-contacts export.
- **headcount-attrition** — B6's monthly workforce snapshot comparison, an
  explicit low-count suppression decision, a raw-row refusal, and a PII sentinel
  scan across landed files, artifacts, and query output.
- **mrr-waterfall** — B7's effective-dated subscription bridge, staged
  same-month classification and deduplication decisions, post-publication
  challenges, and revised-release query checks.
- **product-usage** — B8's rolling-window weekly usage bridge and a staged
  late-arrival lookback decision, graded from a same-workflow refresh.
  Offline-testable only: `live_blocked_reason` refuses live dispatch until
  nxd's stateful readback and workflow-v2 rebuild admission (U1/U2) land.

**Live** is the only tier whose runs cannot be replayed:

- **capability-shortfall** — a mock REST source that genuinely cannot answer some
  of what is asked. The drill is whether the agent refuses the impossible
  metrics, labels the proxy ones, and records those limits as governed decisions
  instead of quietly inventing numbers.

`requires_live_session` makes the deterministic CLI refuse `--tier live` outside
`--mode live`, before loading any package, rather than produce a replay-mode
report indistinguishable from a real one.

A package can also be individually blocked from a live run while remaining
fully loadable, replayable, and unit-testable: `scenario.yaml`'s optional
`live_blocked_reason` field (see `product-usage` above) names an upstream gap
the harness cannot paper over. `scenario.live_blocked` returns every such
scenario in a set; both live-dispatch entry points --
`scripts/run_local_claude.py` and `runner/cli.py` in `--mode live` -- refuse
to start one, whether it was reached through `--tier` or named explicitly
with `--scenario`.

Each scenario's own `README.md` states its fixture, execution, goal, assertions
and limitations.

### Package reference

Use the package README for the exact evidence contract and the boundary of what
the package proves. The canary is a suite preflight, not a conversational
scenario.

| Package | Tier | Run order | Primary source or drill |
|---|---:|---:|---|
| [drift-canary](scenarios/drift-canary/README.md) | preflight | before smoke | skill claims, companion files, negative probes, and a local build outside live workflow-v2 mode |
| [zero-row-optional-output](scenarios/zero-row-optional-output/README.md) | smoke | 1 | file-backed fixture with one valid zero-row optional resource |
| [parent-child-grain-trap](scenarios/parent-child-grain-trap/README.md) | smoke | 2 | generated orders and line items with a parent-grain aggregation trap |
| [credential-rotation](scenarios/credential-rotation/README.md) | core | 3 | disposable Postgres with command-stepped credential rotation |
| [sigterm-diagnosis](scenarios/sigterm-diagnosis/README.md) | core | 4 | deterministic transform-window plan and diagnosis evidence |
| [restart-and-switch](scenarios/restart-and-switch/README.md) | core | 5 | attempt-keyed broker fault and workflow endpoint switch |
| [capability-shortfall](scenarios/capability-shortfall/README.md) | live | 6 | mock REST source with supported, proxy, and impossible metrics |
| [crm-pipeline](scenarios/crm-pipeline/README.md) | core | 7 | paginated mock CRM source with auth expiry, rate limiting, and PII |
| [finance-close](scenarios/finance-close/README.md) | core | 8 | mock close entries with hostile decimals and missing FX |
| [inventory-position](scenarios/inventory-position/README.md) | core | 9 | profile-backed inventory and warehouse lookup with quality warnings |
| [application-reconciliation](scenarios/application-reconciliation/README.md) | core | 10 | 391-to-353 count dispute with status/tombstone lineage |
| [locale-timezone](scenarios/locale-timezone/README.md) | core | 11 | UTF-8 categories and source-local versus UTC boundary evidence |
| [marketing-attribution](scenarios/marketing-attribution/README.md) | full | 12 | safe campaign matching, unmatched-CPA policy, and out-of-scope export sentinel scan |
| [headcount-attrition](scenarios/headcount-attrition/README.md) | full | 13 | monthly headcount and attrition with PII exclusion and small-cell suppression |
| [mrr-waterfall](scenarios/mrr-waterfall/README.md) | full | 14 | effective-dated MRR waterfall with staged decisions and revised-publication evidence |
| [product-usage](scenarios/product-usage/README.md) | full | 15 | rolling-window usage events, late-arrival lookback decision, same-workflow refresh evidence (offline-testable only; blocked from live dispatch) |
| [crm-pipeline-drift](scenarios/crm-pipeline-drift/README.md) | full | 20 | chained CRM source drift, staged ruling, separate publication, and structural warning evidence |

## Running

### Deterministic and replay

```bash
uv run --project evals/dp-scenarios python -m dp_scenarios.runner.cli \
  --tier smoke --scenario-root evals/dp-scenarios/scenarios ...
```

`--tier` is required, and a tier matching no package is an error rather than an
empty, clean-looking run.

### Live

The local-only live entrypoint runs a selected package through Claude Code, the
installed `nxd-desktop` MCP server, and the job-loop skills. At present,
`capability-shortfall` is the only package in the `live` tier. The runner needs
the local `claude` executable, the `nxd-desktop-supervisor` executable, and the
desktop Python environment at `~/.nxd/desktop-venv/bin/python` unless an
explicit `--desktop-python` is supplied. The supervisor's directory must also hold
`nxd-desktop-kernel-host`: the supervisor spawns that sibling only when
validation starts, so the runner checks for it before any agent turn rather
than letting a partial build (such as a `target/ci` holding only the
supervisor) surface mid-run as `workflow/execution_unavailable`. The supervisor
also embeds the skill pack's `src/nxd-run-job-loop/scripts/self_check.py` at
build time (from its `external/nexty-agent-skills` submodule) and retains that
copy in every capture, so the runner refuses a supervisor whose binary does not
contain the staged checker's exact bytes. Without that preflight the run spends
its agent turns and is then invalidated as `checker_skew_mismatch` by the
post-capture comparison, which remains the authoritative check. It does not use
the platform CLI or a Kubernetes cluster.

Before each disposable MCP server starts, the runner activates the bundled
workflow-v2 contract in that trial's supervisor data directory. Activation is
trusted runner configuration, not user consent. The agent must still prepare
the exact blueprint, request the scenario's declared approval turn, and relay
that verbatim approval through `session_decision` before it authors the
closure. Activation failure stops the run; the live runner does not fall back
to `check_data_product` or `build_data_product`. Use
`--workflow-activation-bundle <path>` only when testing another exact trusted
contract.

Each trial gets a disposable home, fixture, skill-pack staging area, and
evidence directory; the report and transcript artifacts are retained under
`--output-dir` or a printed temporary directory. Naming a package with
`--scenario` deliberately crosses the tier boundary. Omitting `--scenario`
runs smoke by default; `--tier live` selects the current live package when no
package is named.

Before a selected `core`, `full`, or `live` Claude run starts its canary or
scenario sessions, the entrypoint performs a non-generative
`claude auth status --json` preflight and checks only `loggedIn`. Its captured
provider response is never printed or persisted. Claude exposes no local
usage/quota API, so a provider session-limit response can still occur after a
successful authentication preflight; such a run remains incomplete evidence,
not a pass.

For long live runs, pass an explicit stable `--checkpoint-dir` to emit a
credential-free, per-turn handoff checkpoint after each completed turn. The
checkpoint identity binds the scenario, script, skill/model, supervisor,
fixture, and grading pins; it fails closed on drift and never overwrites a
checkpoint payload. This is durable handoff evidence, not native Claude
continuation, and it does not claim that B1 passes.

Native provider continuation is a separate, explicit opt-in seam. Add
`--native-continuation --native-run-root <persistent-root>` to a fresh run
(alongside `--checkpoint-dir`). The native checkpoint stores only a canonical
provider session/thread identifier and the SHA-256 execution-identity digest. To resume one
committed prefix, pass `--native-resume-checkpoint` together with the same
persistent run root; the runner replays the committed operator prefix locally,
verifies each message, and asks the selected provider adapter to continue at
the next operator turn in that provider session. Claude uses `--resume
<session-id>`; Codex uses its app-server thread/resume operation. The runner
never sends the committed prefix to the provider again or injects a synthetic
opening prompt.
Redacted touched-file observations are rehydrated only from the retained
workspace and must match their committed hash and size; changed or missing
files reject the resume.

This seam is intentionally bounded: native continuation requires one scenario,
one epoch, `--jobs 1`, the original persistent run root, and an unchanged
checkpoint identity. Route-backed/mock-source environments are supported when
the fresh run persists `native-source-contract.json`; resume validates the
credential-free source contract, checks the current route configuration digest,
and restarts the source on the recorded data/control endpoints. The paired
`native-source-state.json` snapshot restores the non-secret auth budget,
mutable route state, and request counters needed for rate-limit and oracle
continuity; pagination cursors are regenerated from the restored route state.
The snapshot is refreshed after each committed native turn and during orderly
environment cleanup.
Missing, malformed, drifted, or occupied-port state fails closed; the default
fresh-run path and the handoff path are unchanged. This enables B1-style
resumption, but B1 still requires a separate live rerun for evidence. Auth
tokens and control secrets are never persisted.

```bash
uv run --project evals/dp-scenarios python evals/dp-scenarios/scripts/run_local_claude.py \
  --scenario capability-shortfall \
  --epochs 1 \
  --allow-host-home --allow-host-home-bash \
  --output-dir /tmp/dp-scenarios-local-run \
  --checkpoint-dir /tmp/dp-scenarios-local-checkpoints
```

The native continuation flags are deliberately absent from this handoff
example. A native run must name its persistent contract explicitly, for
example:

```bash
uv run --project evals/dp-scenarios python evals/dp-scenarios/scripts/run_local_claude.py \
  --scenario capability-shortfall \
  --output-dir /tmp/dp-scenarios-native-run \
  --checkpoint-dir /tmp/dp-scenarios-native-checkpoints \
  --native-continuation \
  --native-run-root /tmp/dp-scenarios-native-root
```

Each live agent turn defaults to a 1800-second timeout. Retained-capture review
defaults to 600 seconds; its inspection window closes after 540 seconds, leaving
the final 60 seconds for the reviewer to return its findings. These are harness
time budgets, not grading criteria.

`--allow-host-home` exposes the host credential/configuration home to the agent
process. `--allow-host-home-bash` additionally exposes shell access and should
be used only when the scenario needs it; the current capability-shortfall live
path needs it to probe the local HTTP source. Keep the output directory empty
before starting a run. A non-zero exit can mean a failed grade, an
environment/interruption result, or a canary block; read `summary.txt` and the
`interruption` object in `report.json` before rerunning.

`--allow-host-home-bash` cannot be combined with a Claude OAuth token. Unset
`CLAUDE_CODE_OAUTH_TOKEN` (and omit `--env-file`) to grant Bash, or drop the
flag to run token-authenticated without a shell.

Each run writes, next to `report.json` and `summary.txt`:

```
conversation-<scenario>-epoch-<n>.md
```

That is the readable transcript — every operator and agent turn, which rule
answered each one, whether the driver authored it or fell back, the tools the
agent called, and the gate results. Start there when you want to know how a run
actually went; `summary.txt` gives you the verdict and gate codes, and names the
transcripts at the end.

#### Runner-owned supervisor history

Each live Claude epoch also writes these deterministic histories under its
`artifacts/` directory. The existing `supervisor-facts.json` and
`query-results.json` contracts remain unchanged.

- `publication-history.json` — `dp-scenario-publication-history-v1`: session-attributed supervisor releases.
- `run-records.json` — `dp-scenario-run-records-v1`: admissions, run status transitions, and operator-turn attribution.
- `run-failures.json` — `dp-scenario-run-failures-v1`: bounded structured run, operation, and tool-result diagnostics.
- `tool-calls.json` — `dp-scenario-tool-calls-v1`: allowlisted MCP call fields and endpoint-to-workflow mappings.
- `query-history.json` — `dp-scenario-query-history-v1`: turn-attributed structured semantic-query results, capped at 64.
- `supervisor-captures.json` — `dp-scenario-supervisor-captures-v1`: safe snapshot inventory; copied files live under `supervisor-captures/<digest>/`.
- `definition-export.json` — `dp-scenario-definition-export-v1`: compiled manifest promises and inventory metadata for session runs.

Follow-up graders receive a `SupervisorHistoryView` built from exactly these
seven JSON files and the already sanitized capture snapshots. It is read-only,
size-bounded, and joins a release through its run's `definition_id` and
`capture_sha256`; a missing artifact or inconsistent identity cannot be
replaced with the newest unrelated record. A compiled promise's
`source_in_inventory` means only that its path was listed. The separate
`source_hash_verified` flag is true only when the actual contract source bytes
and size match the definition inventory. Existing follow-up kinds can ignore
the new context. A history-dependent handler checks the view's `status` and
uses `rows("publication-history")` plus `linked_release(release)`; that join
raises `HistoryEvidenceError` on conflicting identities or copied-file hashes.
The next scenario package must classify missing or invalid runner history as
ungraded evidence and an absent agent-produced release as a graded failure.

To run several selected scenario packages at once, repeat `--scenario` and set
`--jobs`, for example:

```bash
uv run --project evals/dp-scenarios python evals/dp-scenarios/scripts/run_local_claude.py \
  --scenario zero-row-optional-output \
  --scenario parent-child-grain-trap \
  --jobs 2
```

`--jobs` fans out different scenario packages; epochs within one package stay
serial. Every epoch has its own temporary root and Desktop supervisor data
directory, so this does not rely on one supervisor serving multiple workflows
at the same time. Results remain in scenario declaration order. The effective
worker count is recorded as `max_workers` in `report.json`.

Parallel workers compete for host CPU, memory, subprocesses, and local ports.
That contention can trip `--turn-timeout`, which makes the tier `ungraded`; do
not compare the `Total wall-clock` value in `summary.txt` between serial and
parallel runs as if they were the same execution conditions. The `efficiency`
fields in `report.json` are reported-only turn and call counts; they do not
measure this host contention.

With no `--scenario` it runs the smoke tier rather than every package on disk.
Naming a scenario id explicitly crosses the tier, which is how you run one core
or live scenario live.

CI runs the deterministic harness and replay tests; live qualification is a
developer-controlled local operation.

#### Host credentials and tool exposure

Use `--allow-host-home` only when the host credential store is required. It gives
the entire agent process the real host `HOME`, including any configuration and
credential files its tools can reach. In this mode the runner denies the shell
tools (`Bash`, `BashOutput`, `KillShell`) via `--disallowedTools`.

That flag, not `--allowedTools`, is what withholds a tool. **`--allowedTools` is
an auto-approval list**: a tool merely left off it stays available for a settings
source or permission mode to approve — which is how an earlier run that claimed
"Bash removed" still ran Bash against the real host `HOME`. Add
`--allow-host-home-bash` only when the scenario needs shell access and you accept
that exposure.

The denial covers the shell surface only. Other tools this adapter does not grant
(`WebFetch`, `WebSearch`, `NotebookEdit`) are omitted from `--allowedTools` but
not denied, so treat "not granted" as "not auto-approved", not "unreachable".
Deny rules also apply to a `Task` subagent, so a denied shell stays denied one
level down.

The live runner's optional `supervisor_environment` may carry
`NXD_DESKTOP_TRUSTED_CREDENTIAL_ENVS` as a comma-separated list of
`service=ENVIRONMENT_VARIABLE` names. The mapping contains names only, is limited
to 16 entries and 4096 characters, and duplicate services, malformed entries, or
rebinding the runner-generated `NXD_EVAL_SOURCE_TOKEN` are rejected before the
supervisor starts. An authenticated source uses one of those entries for the
runner-generated mapping, leaving at most 15 caller entries. Each named variable
must also be present in that explicit `supervisor_environment` for the MCP serve
child; ambient shell variables are not inherited by that child. Workflow
activation is a separate supervisor invocation and may use explicitly retained
caller variables. `api-source` is reserved for the runner-generated source and
cannot be mapped to another variable. An authenticated mock API source adds its own
`api-source=NXD_EVAL_SOURCE_TOKEN` mapping for the trusted supervisor child; the
credential value is never placed in the agent environment or workflow activation
environment.

#### Driving the operator with a model

```bash
export OPENAI_API_KEY=...   # the only place the runner reads the key from
uv run --project evals/dp-scenarios python evals/dp-scenarios/scripts/run_local_claude.py \
  --scenario capability-shortfall \
  --driver-model gpt-5.6-luna \
  --output-dir /tmp/dp-scenarios-driven-run
```

| flag | default | meaning |
|---|---|---|
| `--driver-model` | none | model id; omitting it keeps the scripted operator |
| `--driver-backend` | `openai` | `openai` API or locally logged-in `codex` CLI |
| `--driver-effort` | `medium` | Codex reasoning effort |
| `--driver-temperature` | `1.0` | OpenAI sampling temperature, pinned into the manifest |
| `--driver-max-tokens` | `400` | OpenAI completion cap per call, including reasoning tokens |
| `--driver-timeout` | `60` OpenAI, `300` Codex | seconds allowed for one provider call before the turn falls back |

To use ChatGPT login through the local Codex CLI, use
`--driver-backend codex --driver-model gpt-6-sol` (optionally
`--driver-effort medium`). This path does not need `OPENAI_API_KEY`. It sends
the same system prompt, persona, and view as the OpenAI driver, rendered into
one stdin prompt for `codex exec` in an empty temporary directory. The child
gets only `HOME`, `PATH`, optional `CODEX_HOME`, and locale variables. The CLI's
`--ignore-user-config` and `--ignore-rules` flags avoid user config, MCP server
and hook configuration, and exec policy rules; the child also uses an ephemeral
session and a read-only sandbox. The CLI has no supported flag to disable all
built-in agent tools, and host login files remain available to the Codex
process for authentication. Use the default temperature and token cap with this
backend; Codex does not apply them and non-default values are rejected.

The same flags exist on `dp_scenarios.runner.cli`, where they require
`--mode live` — replaying a recording re-authors nothing.

GPT-5-class models accept only the default temperature, so the request omits
`temperature` when it is `1.0` and sends it otherwise. The request always uses
`max_completion_tokens`; those models reject `max_tokens` outright and older ones
accept the newer name. A driven run where every authorable turn shows
`operator_mode: driver_fallback` is this class of problem — the fallback reason
carries the provider's own scrubbed message, so read that first.

**`driver_forbidden_terms` is required.** A driven scenario's answer sheet must
declare the vocabulary the agent is being graded on discovering for itself; the
engine refuses to construct a driver without it.

**What is recorded.** The manifest pins `driver_model_id` and
`driver_sampling_params`. OpenAI keeps its historical `temperature`,
`max_tokens`, and `prompt_hash` fields. Codex adds `backend: codex` and `effort`
alongside the same prompt hash; its temperature and token cap are marked not
applicable (the numeric `temperature: 1.0` remains for the manifest schema).
These fields prevent pairing different operator backends or prompts. Per turn,
`operator-observations.json` carries `operator_mode`,
`operator_beat_id` and the driver flags; the run level carries four counters:

| counter | what it means |
|---|---|
| `driver_leading_rejected_count` | authored turns that used forbidden vocabulary twice and fell back |
| `driver_obstacle_rejected_count` | authored turns the matcher's obstacle validation refused twice |
| `driver_repeat_rejected_count` | authored turns that reproduced a line the engine had already *selected*, twice |
| `driver_beat_substituted_count` | authored turns whose composed message failed to deliver a mandatory event |

The repeat counter is keyed to the engine's own selections (`prior_base_texts`),
not to transmitted text. On a driven run those diverge, so it fires when the
driver reproduces a scripted line verbatim and *not* when the driver repeats
itself: a driver that sends the same sentence three turns running passes with all
four counters at zero.

#### Routing the operator with a model

The regex matcher decides which declared response answers each agent message,
and it misreads asks phrased in unfamiliar markdown shapes. `--operator-router
llm` replaces only that *decision* with a model's:

```bash
uv run python scripts/run_local_claude.py ... \
  --operator-router llm --router-backend codex --router-model gpt-6-sol
```

| Flag | Default | Meaning |
|---|---|---|
| `--operator-router` | `regex` | `regex` is the unchanged, byte-stable matcher; `llm` enables the router |
| `--router-backend` | `codex` | `codex` or `claude` (the locally logged-in CLI; no key in the harness) |
| `--router-model` | required for `llm` | e.g. `gpt-6-sol` (codex), `sonnet` (claude) |
| `--router-effort` | `medium` | reasoning effort |
| `--router-timeout` | `90` | seconds per call before that turn falls back |

For each agent message the router sees the message (sentinel-redacted), the one
before it, and the responses that are *available now*: each unlocked declared
decision (by topic terms, never its answer), `approval`, the review
authorization and review choice while a review is in play, the declared fact,
source and status topics, the persona's deflections, and `none`. It returns one
strict JSON object (`category`, `option_id`, `approval_requested`,
`solicits_operator`, `recommended_option_label`). It never sees gold, tool
results, files, sentinels or any answer text.

The engine keeps everything else: the reply text still comes from the answer
sheet or persona, and answered-once, event/overlay staging, re-approval limits,
forbidden terms and the ledger stay deterministic. Applicable owed beats remain
queued; after a successful governed query confirms publication, obsolete
conditional review or approval beats no longer keep the run open. An id that
was not offered, malformed or inconsistent output, a label the agent never
wrote, a timeout, a provider error, or a decision the engine's answered-once
rule refuses all fall back to the regex matcher for that turn. Rule ids are the existing shapes (`decision.answer.<id>`,
`persona.<category>`, `review.choice_undeclared`, ...). Ledger claims add
`routed_by: "llm"` when the model chose, and `router_fallback: true` when it
did not; the reason is on `MatchResult.router_failure_reason`.

**Grading implications.** A routed run is not deterministic turn for turn, so
replay verification is `not-attempted`, the run is capped below CERTIFIED (like
a driver run), and its `operator_mode` is `llm_router`. The router's backend,
model, effort, timeout and prompt hash are pinned under
`agent_sampling_params.operator_router` in the manifest, so runs with different
routers never compare as identical. Scripted runs (`regex`) are untouched.
Use the router to observe agent behaviour without matcher misreads, not to
certify.

#### Keeping the key around between runs

`evals/dp-scenarios/.env` is gitignored for local credentials. Create it once,
`chmod 600`, and pass it explicitly to the live runner:

```bash
umask 077
cat > evals/dp-scenarios/.env <<'EOF'
OPENAI_API_KEY=sk-...
CLAUDE_CODE_OAUTH_TOKEN=...
EOF
chmod 600 evals/dp-scenarios/.env
```

Confirm the ignore works before pasting a real key:
`git check-ignore -v evals/dp-scenarios/.env` must print a matching rule.

The runner reads only `OPENAI_API_KEY` and `CLAUDE_CODE_OAUTH_TOKEN` from the
file. `--driver-backend openai --driver-model` uses the OpenAI key in the harness;
the Codex driver uses local Codex CLI login. The Claude OAuth
token is passed only across the trusted adapter-to-Claude boundary. It is not
added to the agent session allowlist, the Desktop supervisor environment, the
manifest, or retained artifacts. OAuth-token runs also deny Bash so the agent
cannot inherit the token through a shell. Environment variables with the same
names override the file values.

For a live run, pass the file explicitly:

```bash
uv run --project evals/dp-scenarios python evals/dp-scenarios/scripts/run_local_claude.py \
  --env-file evals/dp-scenarios/.env \
  --scenario crm-pipeline
```

The live runner also supports the host-authenticated Codex CLI as an alternate
agent backend. This is a real provider run through the same supervisor and
grading boundary; it is not a replay and it does not relax any gate. Codex
uses its own workspace-write sandbox and the runner-owned `nxd-desktop` MCP
server. Its default model is `gpt-5.6-luna`; pass `--model` to select another
Codex model. The runner passes only the `CODEX_HOME` directory path to the
child, never credential values or the host HOME:

```bash
uv run --project evals/dp-scenarios python evals/dp-scenarios/scripts/run_local_claude.py \
  --agent-backend codex \
  --scenario crm-pipeline \
  --model gpt-5.6-luna \
  --effort xhigh \
  --codex-home "$HOME/.codex" \
  --output-dir /tmp/dp-scenarios-codex-b1
```

The adversarial reviewer runs as a Codex collaboration child, and Codex picks
the collaboration runtime from the model catalog's `multi_agent_version`.
Under v1 (`gpt-5.6-luna`), `spawnAgent` exposes the dispatch prompt and `wait`
takes `{"targets":[id]}`. Under v2 (`gpt-6-luna` and the other gpt-6 models),
the tools are `spawn_agent` and `wait_agent`. `wait_agent` takes only
`timeout_ms`, and the child's lifecycle arrives as `subAgentActivity` items.
The runner reads the child's final answer from the child thread
(`thread/turns/list`) and records it with the child's thread id. v2 delivers
the spawn message to the child only as provider-encrypted content, so the
dispatch prompt cannot be observed. The canonical reviewer-dispatch gate
therefore cannot credit a v2 reviewer, and
`construction_adversarial_review_not_observed` remains. The optional
`--codex-force-multi-agent-v1` flag stages a copy of the host's cached model
catalog (`$CODEX_HOME/models_cache.json`) with only the selected model switched
to v1, and records that choice in the run's sampling parameters.

Codex sessions use one long-lived `codex app-server --stdio` child per live
run. This keeps the runner-owned MCP connection and opaque provider thread
identity across operator turns; a fresh Codex process is not started for each
turn. Ordinary runs use a disposable Codex home and symlink only the
host-owned auth handle, so host MCP configuration and plugin state do not
enter the run. Native continuation instead keeps the app-server home under
`<native-run-root>/<scenario>/epoch-N/provider-state/codex-home` across runner
processes. That private owner-only state can contain provider transcripts and
tool results; it is outside the agent workspace and evidence bundle, but must
still be treated as sensitive and retained only while a resume may be needed.
The auth handle remains a symlink to the host-owned file; the harness never
copies or reads its contents. Codex native continuation persists the provider
thread identity in the credential-free checkpoint and resumes through the
app-server when the same private run root and execution identity are supplied.
On resume, the runner accepts only Codex's app-written `trust_level = "trusted"`
marker for the run workspace; other project markers and persisted config
changes are rejected. Since that marker can activate project-local Codex
settings, resume also fails closed if the agent workspace contains a `.codex/`
directory. The app-server also excludes `/tmp` and `$TMPDIR` from the
workspace-write sandbox's default writable roots; only the scenario workspace
and skill-pack roots are supplied as explicit writable roots.
Claude-only flags such as
`--max-budget-usd` and Claude tool-grant flags are rejected or ignored for
this backend. Codex's workspace sandbox is provider-owned, so tool-restricted
scenarios are not directly comparable with Claude runs that enforce a
per-tool allowlist.

For Codex live runs, each successful workflow-v2 capture that returns a
supervisor-issued `retained_capture_root` also receives a runner-owned checker
observation. The harness compares the raw bytes of the staged
`nxd-run-job-loop/scripts/self_check.py` with the retained capture's
`self_check.py`: a digest mismatch invalidates the run, while an unreadable or
malformed comparison makes it ungraded. A successful Codex capture with review
input but no marker is also ungraded; this requirement applies only to fresh
Codex live runs. This guard covers only `self_check.py`; skew in other embedded
helpers is not detected. Captures without that path and legacy replays without
checker markers retain their prior grading behavior.

### When a live run stops without being graded

A live run can end for reasons that say nothing about the agent: the provider
declines another turn, the runner's per-run spend cap is reached, the Claude
child stops producing terminal stream results, or two runs contend on the same
runtime state. Those used to reach
the report as `ungraded` and nothing else, which reads exactly like a scenario
defect.

Each interrupted run now carries a closed-vocabulary reason, and every run
carries the block whether or not it was interrupted:

```json
"interruption": {
  "failure_reason": "provider_session_limit",
  "failure_detail": "Claude did not complete the turn within 324.0s",
  "last_mcp_call": "build_data_product:error"
}
```

| `failure_reason` | What happened | What to do |
| --- | --- | --- |
| `provider_session_limit` | The provider refused another turn (usage, rate, or credit ceiling). | Wait for the reset; the scenario is untested, not failed. |
| `run_budget_exhausted` | Claude Code stopped because the runner's configured `--max-budget-usd` cap was reached. | Raise or remove the run-local cap for a deliberate rerun; this run is incomplete, not passed or failed behaviorally. |
| `codex_provider_retry_pending` | Codex reported a retryable provider error, then the root turn produced no terminal result before its deadline. | Inspect the safe variant/status metadata and retry only after provider availability is confirmed; the run is incomplete. |
| `codex_provider_error` | Codex reported a non-retryable app-server error, or a root turn failed without a more specific provider classification. | Inspect the allow-listed variant/status metadata; the run is incomplete. |
| `child_no_terminal_result` | A delegated child did not return a terminal result before its configured reviewer deadline. A `pendingInit` snapshot is not proof that the child is inactive; a matching completed wait clears the deadline. | Check the parent app-server event tail, elapsed/idle timing, reviewer phase, and metadata-only reader summaries before deciding whether a rerun is useful. |
| `codex_root_turn_no_terminal_result` | The Codex app-server root turn stayed alive past its deadline without emitting a root terminal result. | Check the app-server event tail; the run is incomplete and ungraded. |
| `child_exited_early` | The child exited before emitting a `result`. | Read `failure_detail`; usually a startup or config fault. |
| `shared_runtime_contention` | Two runs contended on shared runtime state (locked store, busy port). | Rerun; live canary closures are already copied per run. |

`summary.txt` prints the same three lines, because stdout is where the
decision to rerun or to wait actually gets made.

`environment_wedge` is a coarse stop category, not the diagnosis; use
`interruption.failure_reason` for the specific cause. An invalid run remains
visible as invalid in its scenario row and is never promoted to a pass.

None of these is a pass. A green live run is one whose required gates passed,
not one that stopped politely.

### How a mock source reaches the agent

A scenario whose source is the run-local mock REST server hands it over the way
an operator would: the runner writes an `infra-profile.yaml` into the agent's
workspace with the `base_url` and the endpoints it is documented to serve, and
exports its path as `NXD_EVAL_SOURCE_PROFILE` alongside `NXD_EVAL_SOURCE_URL`.

Only parameter-free `GET` routes that serve a successful body are advertised.
Error-only routes, forbidden writes, and templated paths stay out, so a scenario
that grades honest probing does not find its answer in the handover.

For a stateful mock source, the runner can call
`MockSourceHandle.set_dataset_state(family, state)` after the required observed
event. This uses the same validation as the control port and invalidates cursors
from earlier states. Harness artifacts retain `source-turns.json`, with one
snapshot per completed live turn: selected source states, the last request
sequence, and cumulative safe counters. Each successful page observation in
`server-counters.json` carries its source state and request sequence. Contact
objects are excluded. The older `source-evidence.json` page and transport trace
shapes remain available to existing follow-ups.

An operator decision can declare `stages` instead of one `answer`; each
solicitation receives the next declared answer after the previous answer was
delivered. `available_after_overlay` and `retired_after_overlay` let a chain
controller activate a new ruling and retire an old one at the same boundary.
The runner records
`operator_selected_decision_id/stage/final` for the answer chosen from the
agent's current message and `operator_delivered_decision_id/stage/final` for
the answer actually sent at the start of a turn. Follow-ups that grade an
authorization use the delivered fields; the last selected answer may never
have reached the agent.

A decision can opt into a planted ambiguity with `clarify_first: true`
(a boolean, default `false`). On its first ask, the operator sends the
persona's `decision_request` reply instead of the declared answer. Only an
actually transmitted clarification advances the state, keyed by decision ID;
the next ask for that decision receives its declared answer (or first stage).
The clarification is not recorded as a delivered decision. For example:

```yaml
decision_answers:
  B6-suppression-N:
    terms: [small-group, suppression]
    clarify_first: true
    answer: "Suppress department-month values under five people and mark them as suppressed."
```

An optional `source_answer_terms` mapping declares aliases for existing
`source_answers` keys, for example `period: [baseline, reporting period]`.
The loader rejects undeclared source keys and empty alias lists. In scripted
mode, aliases in explicit request clauses identify secondary source answers
in compound asks. In LLM mode, the router selects secondary source or fact
answers through `additional_option_ids`; the regex matcher does not replace
a valid router choice. Secondary answers remain owed until transmitted,
without replacing the first ambiguity plant or a clarified approval.

For review dispositions, the router returns `recommended_option_labels` in
finding order so the reply accepts each recommendation. The parser also
accepts the earlier singular `recommended_option_label` response shape.

An optional `scenario.yaml` `chain` block declares `trigger: first_publication`,
`prefix_turns`, `source_family`, `from_state`, `to_state`, `decision_overlay`,
and `stage_values`. The loader rejects unknown keys, undeclared overlays, and
states absent from the declared stateful routes. Its contents contribute to
the scenario script hash; existing scenarios retain their prior hash. At each
completed live turn the controller reads runner-owned publication and run
history. The first attributed published release is frozen in
`chain-state.json`; a retained, definition-bound verifier or promised typed
stage model must establish the prefix's executable stage constraint before
the source changes. The source switch precedes overlay activation and the
next operator message. Unused prefix slots are skipped, while a prefix with
no publication never exposes the suffix. The replay records the transition
and per-turn publication snapshots. Chained native resume is refused before
starting a session until controller state can be restored from a checkpoint.

Follow-up handlers receive `FollowUpContext.artifact_root` for runner-owned
history. A missing publication or invalid executable prefix is a failed chain;
retained capture loss and interrupted source switching are ungraded. A chain
record is structural evidence and does not claim an observed verifier warning.

## Adding a scenario

A scenario package is additive: it needs no edit to a shared file, so two
scenarios can be authored in parallel without conflicting.

1. `scenarios/<name>/` — `scenario.yaml` (unique `run_order`, declared `tier`),
   `answer-sheet.yaml`, `events.yaml`, `gold/`, a `.gitattributes` file that
   protects the committed gold extensions from LFS filtering, and a `README.md`
   stating the fixture, execution, goal, assertions and limitations.
2. `src/dp_scenarios/followups/<kind>.py` — the follow-up check. Define
   `check(scenario, target, settings, context)` and `register()` a `FollowUpKind`
   naming its gold keys, any certification gold, and a settings validator.
   `followups/__init__.py` imports every module beside it, so nothing needs to
   list the new kind.
3. `tests/test_scenario_<name>.py` — property tests. **Mutation-test them:** break
   each check and confirm a test fails. Reading a diff has never caught a real
   defect in this suite; mutation has. For the operator and grading directories
   this is automated — see [Mutation testing](#mutation-testing) below. A
   follow-up check lives outside those directories, so mutating it is still a
   hand job; the section below says how to do one that cannot lie to you.

The loader tests derive the expected package set from disk, so a new package
needs no test edit either.

## Mutation testing

The acceptance bar for a check in this suite is not "the tests pass", it is
"break the check and a test fails". Two failure modes make that bar hard to hold
by hand.

A hand-rolled mutation can **silently fail to apply** — a regex that misses its
target line, a `str.replace` that no-ops — and the run that follows is green for
the boring reason, not the interesting one. That has twice produced a confident
wrong conclusion here, once reporting a guard as unenforced when the guard was
fine. And nobody hand-mutates code they did not just write, so the failure this
harness actually keeps producing goes unlooked-for: **a gate that exists but
never fires**, and **a test that asserts the code's self-report rather than the
property**.

`scripts/mutation_test.py` drives [mutmut](https://github.com/boxed/mutmut) over
`src/dp_scenarios/operator/` and `src/dp_scenarios/grading/`. mutmut rewrites
each function into a numbered set of variants behind a generated trampoline and
selects the variant by environment variable, so a mutant that did not apply
cannot be reported as a result at all — the first failure mode is structurally
impossible. Scope, copy rules and pytest arguments live in `[tool.mutmut]` in
`pyproject.toml`.

```bash
cd evals/dp-scenarios

# Everything in the two guarded directories. Hours -- see Runtime.
scripts/mutation_test.py full

# Only the guarded files this branch changes. Run this before merging a change
# under the guarded directories -- CI will not do it for you until nightly.
scripts/mutation_test.py changed --base origin/main

# One mutant, or one function, reproducing a CI failure verbatim.
scripts/mutation_test.py filter 'dp_scenarios.grading.scans.x_supported_path_scan__mutmut_31'
```

**Run it from `evals/dp-scenarios/`.** mutmut reads its config from the
`pyproject.toml` in the working directory, copies the tree into `./mutants/` and
runs the suite from there. The wrapper `cd`s for you, so it can be invoked from
anywhere; bare `uv run mutmut` cannot.

### Reading the result

A **surviving** mutant is a change to the guarded code that the whole suite still
passes with. That is the finding. Each one is a genuinely equivalent mutant, a
missing test, or a bug — and calling one equivalent is a claim that needs an
argument, not a shrug.

A **no tests** mutant counts the same. It means the covering-test analysis found
nothing that executes that function, which is what a newly added function with
no test at all reports. Treating it as merely informational would let a change
add a completely unexercised gate and still go green — the exact defect this
tooling exists to catch.

Runs are compared against `mutation-baseline.json`, a per-function count of
mutants the suite does not notice, and the nightly run fails only on counts
that go **up**. The baseline is keyed by function rather than by mutant name because
mutmut numbers mutants positionally: editing a function renumbers all of its
mutants, so a name-keyed baseline would go red on every edit for reasons that
have nothing to do with test quality. Regenerate it with
`scripts/mutation_test.py full --update-baseline`, and say in the PR why each
added entry is acceptable.

**Regenerate it on Linux, never on macOS.** A macOS run leaves a third of its
mutants unverdicted (below), so a baseline recorded there understates the count
for every function whose covering tests reach fixture generation — and an
understated baseline makes the next Linux run red for work nobody did.

**Record it on `main`, never on a branch.** A baseline describes the exact tree
it was measured against. The first one was recorded on a branch (153 functions,
2741 unnoticed mutants) and invalidated by the rebase that followed, which added
five functions inside the guarded directories. A stale baseline is worse than
none — it has no entry for new code, so every unnoticed mutant there reads as a
regression introduced by whoever merges next.

The current file was recorded by the workflow itself, from a whole-scope Linux
run on `main` (run 33969998522, 238.6 min): **157 functions, 2652 survived and
108 with no tests**, with `timeout`, `suspicious` and `segfault` all zero, so
every mutant reached a verdict and no count in it is understated.

To re-record it, run the workflow by hand with its `update_baseline` input set.
It writes the file from that run and uploads it as the `mutation-baseline`
artifact; download it, commit it, and say in the PR why each *added* entry is
acceptable. Lowering a count needs no baseline edit at all. No local four-hour
run is needed, and the result describes the tree it will be compared against.

With **no** baseline file at all, a run fails on nothing and says so. The first
run on a fresh scope must not report every long-standing gap as something the
change in front of it introduced.

### Runtime, and what actually costs the time

A **killed** mutant is cheap and a **surviving** one is expensive. mutmut runs a
mutant's covering tests fastest-first and stops at the first failure, so a
killed mutant usually costs one fast unit test; a survivor pays for every test
that touches the function, and in this suite that includes the tier tests, which
generate a fixture from the seeded generator on each call. The whole-scope
runtime therefore tracks the *survivor* count, not the mutant count, and it
falls as tests are added.

| Run | Machine | Wall |
|---|---|---|
| suite baseline | macOS, 14 cores | 47s |
| whole scope, 7930 mutants | macOS, 14 cores | 2m25s — but see the macOS caveat below; a third of those mutants crashed instead of running their tests, so this figure is not comparable |
| suite baseline | Linux container, 14 vCPU | 77s |
| whole scope, 7930 mutants | Linux container, 14 vCPU | **2h39m** (5189 killed, 2633 survived, 108 untested, 0 unverdicted) |
| whole scope, 8077 mutants | GitHub hosted runner | **3h59m** (5317 killed, 2652 survived, 108 untested, 0 unverdicted) |
| one module (`grading/scans.py`) | GitHub hosted runner | **15m24s** (1.42 mutants/s, 0 unverdicted) |

The 8077-mutant row is the authoritative one — current tree, and the same class
of machine CI actually uses. It is what sizes `timeout-minutes: 350` in the
workflow, and what the weekly tier costs. The two 7930-mutant rows are from the
pre-rebase tree and are kept only for the machine-to-machine comparison.

That last row is why this does not run on pull requests. `grading/scans.py` is
close to the worst case for a single-module run — a large module with a lot of
survivors — and `grading/gates.py` is the other; a module with fewer survivors
is minutes. Fifteen minutes on the PRs that touch the guarded code was judged
too much to add to the critical path. `changed` mode runs as the nightly tier
instead, and locally before you merge.

Two levers were tried and rejected:

- **`max_stack_depth`**, which would associate each function only with tests
  that call it near-directly, is broken in mutmut 3.7.0: it calls
  `Path(filename).resolve(strict=True)` on every stack frame and raises
  `FileNotFoundError` on the synthetic `<string>` frames that generated code
  produces. Setting it aborts the run during stats collection.
- **Deselecting the fixture-generating tests.** `tests/test_grading_gates.py` is
  one of them, and it is the primary test file for the largest guarded module.
  Dropping it would buy speed by removing exactly the coverage the tier exists
  to measure.

The lever that would actually work is in the suite rather than in mutmut:
`populated_parent_child_recordings` and its neighbours in
`tests/test_runner_tier.py` regenerate a fixture on every call. Caching them
would speed up the ordinary suite as well, and — because mutmut forks each
mutant from a warm parent — a cache populated during stats collection would be
inherited by every mutant for free.

### Where it runs

Both tiers live in `.github/workflows/nightly-mutation.yml`, on disjoint days.
There is a single `cron:` entry; the day of the week picks the tier inside the
job, so there is no schedule literal to keep in sync with a shell comparison.

| Tier | Trigger | Scope |
|---|---|---|
| nightly | 04:10 UTC, Mon-Sat | only guarded modules not yet covered by a green run |
| weekly | 04:10 UTC, Sunday | every mutant in both guarded directories |
| manual | `workflow_dispatch` | whole scope, or the `scope` input's filters |

**Nothing runs on a pull request.** A single-module run costs 15m24s on the worst of
the guarded modules (measured, hosted runner), which is too much to add to the
critical path of every PR that touches them. The gate is nightly instead.

The nightly tier resolves its own base rather than diffing against a branch: the
job runs *on* `main`, so a `--base origin/main` diff would compare `main` against
itself and find nothing every time. It starts from a 26-hour clock window — 26
and not 24 because the scheduler fires late under load, and an overlap only costs
time — then **floors that at the last successful run of the workflow**, whichever
is older. A day with no guarded change exits 0 without invoking mutmut at all.

The floor is the part that matters, and a bare clock window would be a bug
without it. Under a bare window a merge is in scope for exactly one morning. So
if that run is delayed, dropped (GitHub drops scheduled events under load, and
disables schedules entirely after 60 days of repository inactivity) or dies on an
infra flake, the day's merges go unmeasured until Sunday — and worse, **a run
that goes red comes back green the next morning with nothing fixed**, because the
offending module has aged out of the window. That is this suite's "a gate that
exists but never fires" defect in its most deniable form: it fires once, then
un-fires. Flooring at the last green run means an uncovered night widens the next
night's scope, and a red night stays red until someone acts on it.

Two filters make that work. `--status success` is a conclusion filter, so a red
or cancelled run does not advance the floor. `--event schedule` is what makes
"successful" mean "covered": a green run is not evidence of coverage on its own,
because a `scope` dispatch gates only the functions its filter names, and an
`update_baseline` dispatch returns 0 *before* the comparison runs, so it gates on
nothing and can never be red. Both tiers are schedule events and each covers the
range it claims, so **only they advance the floor — a manual dispatch never
does**, and firing one during triage cannot narrow a later nightly.

If the `gh` lookup fails for any reason (no `actions: read`, a force-push having
orphaned the recorded SHA, or a floor somehow *newer* than the clock window), the
clock window stands rather than the scope narrowing.

**Why a weekly whole-scope run still earns its four hours.** The nightly tier only
sees modules the diff names, so it cannot see a survivor created from a distance:
delete the one test that killed a mutant in a module nobody touched and every
nightly stays green. The weekly run is what closes that gap. It arrives up to
seven days late, which is the price of not paying four hours a night.

Both tiers compare against the same whole-scope `mutation-baseline.json`, and the
nightly's narrow scope needs no baseline of its own: `regressions()` iterates the
counts a run actually *observed*, so a scoped run compares only the functions it
measured and never has to explain away the ones it skipped.

The cost is what it is because every run pays a fixed price first: mutmut copies
the tree and traces the suite once to build the function-to-covering-tests map.
After that, time tracks *survivors* rather than mutants — a killed mutant stops
at its first failing test, while a survivor pays for every covering test — so
the number falls as coverage improves.

What this trades away is worth stating plainly: a change that adds an untested
gate merges green and is caught the following morning rather than on its PR. The
nightly tier keeps that cheap to act on -- a red run covers one day of merges, so
attribution is usually a one-PR question -- but a red *weekly* run can span a
week of them, and then you are bisecting. Run
`scripts/mutation_test.py changed --base origin/main` locally before merging
anything under the two guarded directories, and read the nightly result the day
after a merge that touches them. A scheduled run that goes red -- or that is
cancelled, including by the 350-minute cap -- posts a Slack notification
linking the run and naming the survivor report to open.

### Two things that will mislead you

**On macOS, roughly a third of mutants report `segfault` and get no verdict.**
`dp_scenarios.synthgen.reference` opens an in-memory SQLite database, and
`sqlite3.connect` crashes in a `fork()`ed child on macOS — mutmut runs each
mutant in a forked child, so every mutant whose covering tests reach fixture
generation dies before it is judged. Six lines reproduce it with no mutmut
involved:

```python
import os, sqlite3
if os.fork() == 0:
    sqlite3.connect(":memory:")   # SIGSEGV on macOS, fine on Linux
    os._exit(0)
```

Linux is unaffected, so **CI is the authoritative run** and a local macOS score
is a floor, not a measurement. A local survivor is still a real survivor; a local
`segfault` is "not measured".

**A flaky test makes every mutant look killed**, which is the worst possible
outcome: perfect coverage reported by a suite that tested nothing. Two
back-to-back whole-scope runs on identical source disagreed on **2 of 7930**
mutants (0.03%), both at the segfault boundary above. That is low enough to gate
on, and it is worth re-measuring after any change that adds sleeping, real
sockets, or wall-clock assertions to the suite: run
`scripts/mutation_test.py full` twice and diff the two `mutation-report.txt`
files.

### When to still mutate by hand

The automated scope is deliberately narrow. Everything else — `followups/`,
`runner/`, `scenario.py`, `ledger/`, and the scenario packages themselves —
still expects the manual discipline, and so does any check whose property is not
expressible as a source edit at all (a fixture value, a gold row-set, a
scenario's declared order). When you do it by hand, **confirm the mutation
applied** before you believe the result: `git diff` the file you edited, and
check that the test you expected to fail is the one that failed. A green run
after a mutation that did not land is the exact mistake this tooling exists to
remove.

## Runtime control plans

`TierRunner` accepts an epoch-keyed `knob_plan`, so fixed transform latency and
attempt-keyed broker faults are applied before the environment starts and are
pinned in each run manifest. The CLI accepts the same controls from
`--knob-plan`, using either this outer shape or its inner `scenarios` object:

```json
{
  "scenarios": {
    "scenario-id": {
      "1": {
        "transform_window": {
          "naive": {"name": "naive", "calls": 8},
          "bounded": {"name": "bounded", "calls": 1},
          "per_call_latency_ms": 5,
          "route_keys": ["GET /market-data"]
        }
      }
    }
  }
}
```

Workflow switching remains a programmatic control because its replacement
transport and endpoint observation must be supplied by the caller. A CLI plan
declaring one is rejected rather than silently running with the switch off.

## Approval boundary

Every shipped scenario declares exactly one explicit approval turn before
code generation. The operator sends that line verbatim; the agent cannot replace
it with a paraphrase or manufacture approval from its own response. A qualifying
workflow-v2 observation must prepare the blueprint before that turn and relay the
same text through `session_decision` before capture, review, trusted validation,
and admission.

Live runs enforce this sequence in the supervisor. Replay runs do not start a
supervisor, but their recorded evidence must contain the same workflow-v2 calls
and ordering; legacy check/build observations are not accepted as construction
or publication proof. Mapper approval remains a separate supervisor admission
boundary.

## Which skill pack is under test

The canary takes `--skills-root` and has no default. The pack it measures is the
one installed in the isolated environment the agent under test runs in — a build
pinned in the run manifest alongside the supervisor binary and the runtime wheel.

There is deliberately no fallback to a globally installed pack. A global install
drifts from the build an agent actually runs, so a default pointing at one would
measure text no runtime ever saw and report drift the agent could never hit,
while hiding drift in the pack that matters.

## Layout

| Path | Contents |
|---|---|
| `src/dp_scenarios/ledger/` | Evidence ledger, run manifest, ledger lint |
| `src/dp_scenarios/synthgen/` | Seeded fixture generator + gold reference implementation |
| `src/dp_scenarios/mockrest/` | Configurable HTTP mock source |
| `src/dp_scenarios/operator/` | Multi-turn operator: script matcher, generated surface, driver |
| `src/dp_scenarios/grantkit/` | Native field-mapper grant fixtures, cumulative budget ledger, profile delegation |
| `src/dp_scenarios/grading/` | Mechanical gate checks and oracles |
| `src/dp_scenarios/canary/` | Drift-canary claims extraction and verdict matrix |
| `scenarios/` | Per-scenario fixtures, operator scripts, gold row-sets |
| `scripts/` | Local live runner, conversation renderer, mutation-test driver |
| `tests/` | Unit tests for the harness itself |
| `mutation-baseline.json` | Known surviving mutants per function — 157 functions, 2760 unnoticed mutants, recorded on Linux in CI. Both tiers fail on any count that goes **up**; see Mutation testing before adding an entry |

## Fixture hygiene

Large or hostile fixtures are **generated at harness start** from the seeded
generator, not committed. Only small hand-inspectable goldens are committed, and
every committed fixture directory carries a `.gitattributes` exempting the file
types it holds from LFS filtering — a fixture stored as an LFS pointer is read by
the parser as content, and the failure surfaces as a malformed fixture rather
than a missing one. Verify with `git check-attr filter -- <path>` (expect
`unset`) and by reading the staged blob (`git show :<path>`), never the working
tree, which looks correct either way.

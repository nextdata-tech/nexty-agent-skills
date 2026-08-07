---
id: 2026-08-06-credential-intake-boundary
date: 2026-08-06
label: "credential intake asks for slot names; the value reaches infra-profile.yaml off-transcript"
plugin_version: 0.36.6
status: NO_EVAL
scenarios: []
record: null
---
# Benchmark — credential intake asks for slot names; the value reaches infra-profile.yaml off-transcript

## Notes

No eval arm exists and none can be built honestly. Grading this would require a
scenario that hands an agent a credentialed source and then scores whether a live
secret appears in the transcript — which means either seeding a real credential
into a public scenario, or seeding a fake one and grading a string match that
proves nothing about the behavior with a real one. Both make the evidence worse
than no number. The behavior is pinned by a plain-pytest doc gate instead, which
is how every other `evals/tests/` gate in this pack pins guidance that only an
agent turn would exercise.

**What was wrong.** `reference/source-materialization.md` told the agent to
record, at Step 1 intake, "the live token/key if auth is required" (REST API) and
"the live credentials supplied now" (database). Every credential rule in the pack
bound the agent's own *output*: never narrate a token
(`nxd-generate-data-product/reference/api-source.md`), never write one into
`dp-spec.md`, redact one out of a probe traceback before it reaches chat. Nothing
bound the agent's *input*. So the natural reading of the intake instruction — ask
the user for the token — put the secret in conversation history, and the closure's
`SENSITIVE` / `.gitignore` / `chmod 0600` guards do not reach there.

**The pack had already solved this once, at the other boundary.**
`reference/scheduling.md` forbids handing a credential to a subagent because it
"would copy a secret into a second transcript", and prescribes the remedy:
placeholder in `attributes`, `credential_slots` (key names only) on the return,
real value injected host-side before the build. The main thread is also a
transcript. This change extends the same discipline to the human boundary rather
than inventing a second mechanism:

- Intake records the credential's **shape** (slot names per scheme —
  `auth_token`, or `auth_username` + `auth_password`, per `api-source.md`), never
  its value.
- Three ordered routes to `infra-profile.yaml`, cheapest exposure first: (1) the
  agent writes a placeholder and the user fills it in — the human-boundary form of
  the subagent hand-back, into a file that is already `0600`, gitignored and
  `SENSITIVE`; (2) an env var substituted at write time; (3) a chat paste as a
  disclosed last resort, rotated afterward.
- Route 2 carries the qualifier that makes it real: substitute by reading
  `os.environ` **inside** the script, never as a shell-expanded `$TOKEN` on a
  command line — which lands the value in the transcript exactly as a paste does.
  "Use an env var" without that clause is not a fix, and is the shape a reworded
  doc would most plausibly regress to.
- `SKILL.md`'s credential bullet now says "never in chat" covers a value you
  *invited* there, not only one you echoed.

Ordering is load-bearing and is asserted as such: a doc naming the same three
routes with the paste first would satisfy every keyword check while teaching the
opposite behavior, so the gate compares their positions rather than their presence.

Nothing downstream needed to change. `api-source.md` already reports the
connectivity dry-run as **not run** when credentials are absent in-session, which
is exactly the placeholder state route 1 produces; and the `SENSITIVE` /
`.gitignore` trigger is structural — any `*-source` service with a populated
`attributes` list — so a placeholder still emits the guards.

## Evidence

- `evals/tests/test_credential_intake_boundary.py` — 5 tests pinning slot-name
  intake, the ordered routes, the `os.environ`-inside-the-script qualifier, the
  paste disclosure/rotation, and the SKILL.md invited-value rule. Verified to fail
  against the previous implementation: all 5 fail with the two docs restored to
  their `main` versions (`git checkout main -- src/nxd-run-job-loop/SKILL.md
  src/nxd-run-job-loop/reference/source-materialization.md`), including the two
  negative assertions that pin removal of the "live token/key" and "live
  credentials supplied now" intake instructions.
- `python3 -m pytest evals/tests` — green on the rebased branch (688 passed,
  1 skipped). This change contributes exactly the 5 tests named above and
  modifies no existing test; the absolute total also carries the flat-secrets
  work and everything merged from `main`, so the 5-test delta, not the total, is
  what this entry claims.
- `python3 scripts/validate_skills.py --root .` — passes for every tracked skill;
  `src/nxd-run-job-loop/SKILL.md` is 500 lines, at the cap (main was 498), which
  constrained how much of the routing prose could live there rather than in the
  reference.
- `./build-skills.sh` — packages, 200-entry cap respected.
- Version lockstep: 0.36.5 → **0.36.6** (patch — a behavior tightening in an
  existing skill, matching `0e93e3e`'s precedent for the `api-source.md` auth
  dispatch fix), synced across `.claude-plugin/plugin.json`,
  `.claude-plugin/marketplace.json`, and all 17 `src/*/SKILL.md`
  `metadata.version` values. No skill added, so `current_pack` and the README
  table are unchanged.

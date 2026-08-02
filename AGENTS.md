# nexty-agent-skills — authoring & review contract

This file is the canonical contract for changes to the Nexty AI Pro skill pack.
It is agent-neutral: it applies to any assistant editing this repo (Claude Code,
Cursor, Codex, or a human). `CLAUDE.md` includes this file. The PR review
(`.github/workflows/pr-review.yml`) reads it too. The mechanical, build-breaking
subset is enforced by `scripts/validate_skills.py` in CI; the rules below add
pack-level invariants CI cannot check on its own.

## Layout

- `src/<skill>/SKILL.md` — one skill per directory. The directory name is the
  skill's identity; `name:` in frontmatter must match it.
- `src/<skill>/reference/` — progressive-disclosure detail (singular `reference`,
  never `references`).
- `.claude-plugin/plugin.json` + `.claude-plugin/marketplace.json` — plugin and
  marketplace manifests for the Claude Code distribution path.
- `evals/skill-sets.yaml` — named skill packs used by the eval harness.
- `build-skills.sh` — packages each `src/<skill>` into a Claude Desktop zip.
- `.github/workflows/release.yml` — publishes those zips on a `v*` tag.
- `experiments/<name>/` — self-contained prototypes. **Not part of the shipped
  pack**: nothing under `src/` imports them, `build-skills.sh` does not package
  them, and `validate_skills.py` does not scan them, so the versioning and
  pack-completeness rules below do not apply to changes confined here. Each
  carries its own docs — start with
  `experiments/field-mapper/ARCHITECTURE.md`. An experiment that graduates moves
  its code under `src/` and its architecture doc to `docs/architecture/`; until
  then treat `experiments/` as a staging area, never as a dependency.

## Versioning (single source of truth)

The plugin version in `.claude-plugin/plugin.json` is authoritative.

- A `vX.Y.Z` release tag MUST equal `plugin.json` `version` (release.yml enforces).
- `.claude-plugin/marketplace.json` plugin `version` MUST equal `plugin.json`.
- Every `src/*/SKILL.md` `metadata.version` MUST equal the plugin version — skill
  versions are kept in lockstep, not bumped individually.
- Bump the plugin version when shipping new or changed skills (minor for added
  capability, patch for packaging/doc fixes). Sync all three surfaces in the same
  PR.

## Pack completeness (shipped pack = every skill)

The shipped pack is `current_pack` in `evals/skill-sets.yaml`. It must list **every**
skill directory under `src/`. When you add a skill you MUST, in the same PR:

1. Add `src/<skill>` to `current_pack` in `evals/skill-sets.yaml`.
2. Add a row to the **Available Skills** table in `README.md`.
3. Set its `metadata.version` to the current plugin version.

A skill that exists under `src/` but is missing from `current_pack` or the README
table is a release defect — the pack ships incomplete.

## Skill conventions (also enforced by validate_skills.py)

- `name:` lowercase + hyphens, 1–64 chars, matches the directory name.
- `description:` specific, under 1024 chars, includes a `Use when ...` trigger,
  and contains **no angle-bracket placeholders** (`<DP>`) — they trip the loader.
- `allowed-tools:` present, non-empty, minimal, only known Claude Code tools.
- `metadata.version` is semver `X.Y.Z` (and, per above, equals the plugin version).
- `SKILL.md` under 500 lines; detail goes to `reference/`.
- Reference files over 100 lines start with a `## Contents` section in the first
  20 lines.
- Each skill zip stays under the **200-entry Claude Desktop cap** (`build-skills.sh`).

## Before opening a PR

```bash
python3 scripts/validate_skills.py --root .   # conventions
./build-skills.sh                             # packaging + 200-entry cap
```

When a PR changes a skill's behavior (not pure packaging/typo fixes), benchmark
it and commit the evidence: run the relevant eval scenario(s) before and after
(`evals/run.py --report ...`), then record the comparison with
`evals/benchmark_record.py`, which appends to `evals/benchmarks/ledger.md`.
The ledger is the repo's before/after history of skill quality and efficiency
(judge checks, turns, tool calls, tokens) — see "Benchmarking a skill change"
in `evals/README.md`.

## Safety

- Keep the pack self-contained: no files required outside this repo, no customer
  names, secrets, internal URLs, or generated data-product outputs.
- Private evals stay under `evals/private/`; nothing customer-specific in public
  evals.

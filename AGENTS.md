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
- `build-skills.sh` — packages each `src/<skill>` into a Claude Desktop zip and
  assembles the two named uploadable plugin zips,
  `build/nexty-desktop-v<version>.zip` and `build/nexty-datamesh-v<version>.zip`,
  plus the compatibility aggregate `build/nexty-agent-skills-v<version>.zip`.
  Each uses the Desktop/Cowork layout: `./skills/<name>/` trees plus a
  `.claude-plugin/plugin.json` with the `skills` override stripped, because
  Desktop auto-discovers `./skills`. Membership comes from the explicit skill
  lists in `.claude-plugin/marketplace.json`; `src/` remains canonical and
  shared skills may intentionally occur in both named sets.
- `build-plugin.sh` — packages the legacy aggregate `.claude-plugin/plugin.json` +
  `src/` + `README.md` into one direct Claude Code plugin zip,
  `build/plugin/nexty-agent-skills-plugin-v<version>.zip`, in the documented
  plugin format: plugin-root contents at the archive root, loadable with
  `claude --plugin-dir <zip>` / `--plugin-url <url>`. This is the sibling of the
  whole-pack zip above, not a duplicate of it — same skills, the other
  distribution path, which is why it keeps the `skills` → `./src/` override
  Desktop drops. `marketplace.json` is excluded on purpose — it describes the
  marketplace *containing* this plugin (the git install path), and bundling it
  makes `claude plugin validate` resolve the directory as a marketplace and skip
  the plugin manifest. Not a release asset, and it writes to `build/plugin/` to
  stay that way: `release.yml` uploads `build/*.zip` and `build-skills.sh` opens
  by deleting `build/*.zip`, so at the top level this bundle would both ride
  along as a release asset and get silently wiped depending on run order. Both
  globs are non-recursive, so the subdirectory settles it. It keeps the
  examples submodule whole (no
  200-entry cap on this path), validates the unpacked artifact with
  `claude plugin validate --strict` when the CLI is present, and fails closed
  when the submodule is uninitialized, when the two manifest versions disagree,
  or when `plugin.json`'s `skills` field no longer points at `./src/`.
- `.github/workflows/release.yml` — publishes those zips on a `v*` tag.
- `experiments/<name>/` — self-contained prototypes. **Not part of the shipped
  pack**: nothing under `src/` imports them, `build-skills.sh` does not package
  them, and `validate_skills.py` does not scan them, so the versioning and
  pack-completeness rules below do not apply to changes confined here. Each
  carries its own docs. An experiment that graduates moves its code under `src/`
  and its architecture doc to `docs/architecture/`; until then treat
  `experiments/` as a staging area, never as a dependency. The worked example of
  a graduation is the field mapper, which graduated twice: out of `experiments/`
  into the skill, then out of this repo entirely. Its code now ships in the
  `nxd` package as `nxd.experimental.field_mapper`; what stays here is its
  normative contract (`src/nxd-generate-data-product/mapper/CONTRACT.md`), its
  fixtures, and its design record at `docs/architecture/field-mapper.md`.

## Versioning (single source of truth)

The plugin version in `.claude-plugin/plugin.json` is authoritative.

- A `vX.Y.Z` release tag MUST equal `plugin.json` `version` (release.yml enforces).
- `.claude-plugin/marketplace.json` plugin `version` MUST equal `plugin.json`.
- The `nexty-desktop` and `nexty-datamesh` marketplace entries MUST be skill-bundle
  projections from `./src`, and their union MUST cover every skill under `src/`.
- Every `src/*/SKILL.md` `metadata.version` MUST equal the plugin version — skill
  versions are kept in lockstep, not bumped individually.
- Bump the plugin version when shipping new or changed skills (minor for added
  capability, patch for packaging/doc fixes). Sync all three surfaces in the same
  PR.

## Pack completeness (compatibility pack = every skill)

The compatibility pack is `current_pack` in `evals/skill-sets.yaml`. It must list
**every** skill directory under `src/`. The `nexty_desktop` and `nexty_datamesh`
sets describe the two experience-specific projections and may overlap on shared
foundation skills. When you add a skill you MUST, in the same PR:

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
- Each individual skill zip stays under the **200-entry Claude Desktop cap** (`build-skills.sh`).

## Before opening a PR

```bash
python3 scripts/validate_skills.py --root .   # conventions
./build-skills.sh                             # packaging + 200-entry cap
```

**Evals on a PR are opt-in.** The `evals-pr` job runs only while the PR carries
the `run-evals` label; without it, no agent run happens and the PR spends no
model tokens. Add the label to any PR that changes skill behavior — a green
unlabelled PR means the scenarios never ran, not that they passed. The label can
be added after the PR is open and will fire a run on its own.

The unconditional gate is at release, not on the PR: tagging `vX.Y.Z` runs every
runnable public scenario on the tagged commit, and a confirmed regression fails
the release outright. A green run additionally attaches the `evals.json` asset
that the nxd monorepo requires before it will merge a submodule bump — so an
emergency `skip_evals` release still publishes, but cannot reach the monorepo.
See "What runs in CI vs. what only runs locally" in `evals/README.md`.

When a PR changes a skill's behavior (not pure packaging/typo fixes), benchmark
it and commit the evidence: run the relevant eval scenario(s) before and after
(`evals/run.py --report ...`), then record the comparison with
`evals/benchmark_record.py`. It creates a paired measured entry at
`evals/benchmarks/entries/<id>.md` and compact report at
`evals/benchmarks/records/<id>.json`, then deterministically rebuilds
`evals/benchmarks/README.md`. The historical `evals/benchmarks/ledger.md` and
all pre-existing `records/*` are frozen evidence; never append to or rewrite
them. CI runs `benchmark_record.py --check` to validate entry frontmatter and
index freshness.

**When no scenario can distinguish the change**, hand-author a new entry under
`evals/benchmarks/entries/` with frontmatter `status: NO_EVAL`,
`scenarios: []`, and `record: null`. Its Notes must explain why no arm exists,
and its Evidence must name an existing carrying test file path (prefer tests
verified to fail against the previous implementation). Run
`python3 evals/benchmark_record.py --rebuild-index` afterward. Manufacturing a
scenario to produce a number for such a change makes the evidence less
trustworthy, not more.

The generated entry index is the current before/after history of skill quality
and efficiency (judge checks, turns, tool calls, tokens); the legacy ledger is
an immutable historical record. See "Benchmarking a skill change" in
`evals/README.md`.

## Safety

- Keep the pack self-contained: no files required outside this repo, no customer
  names, secrets, internal URLs, or generated data-product outputs.
- Private evals stay under `evals/private/`; nothing customer-specific in public
  evals.

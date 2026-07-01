# NEX-730 — `nxd skills`: first-party skill install + auto-sync

Design for productizing nexty-agent-skills installation into the `nxd` CLI,
serving skill content from the existing installer pod, auto-updating on the same
rails as the CLI self-updater.

## Scope

Claude-family only: **Claude Code**, **Claude Desktop**, **Claude Cowork**.
(Cursor/Copilot/etc. read incompatible formats — a separate adapter feature, out
of scope.)

## Decisions (locked)

| Axis | Decision |
|------|----------|
| CLI surface | New `nxd skills` subcommand (Rust, `components/cli`) |
| Content source | HTTP from the existing `nxd-cli-installer` nginx pod |
| Auto-update | Silent self-heal on `nxd` startup — mirrors `update::version_check` |
| Auth / version / fetch / cadence | **Identical to the CLI self-updater** (`update.rs`) |
| Desktop/Cowork install mechanism | Marketplace-cache injection (proven NEX-730, survives restart) |
| Claude Code install mechanism | Same marketplace-cache schema under `~/.claude/plugins/`, OR loose `~/.claude/skills/` (see Open Q1) |

## The install mechanism (already proven, see install.sh)

Desktop/Cowork load plugins from a local marketplace store under
`~/Library/Application Support/Claude/local-agent-mode-sessions/<acct>/<dev>/`.
Install = materialize a marketplace dir + plugin cache, then register across
**three** files (all atomic, all backed up):

1. `known_marketplaces.json` — `{nexty:{source:{github,repo},installLocation,lastUpdated}}`
2. `installed_plugins.json` (version:2) — `{"nexty-agent-skills@nexty":[{installPath,version,gitCommitSha,...}]}`
3. `cowork_settings.json` — `enabledPlugins["nexty-agent-skills@nexty"]=true` (+ `extraKnownMarketplaces` mirror)

Critical gotchas (encoded in install.sh, must carry into Rust):
- The cached `plugin.json` MUST NOT have a `skills` key — it overrides the
  `./skills/` auto-discovery and the plugin loads empty.
- The enable flag lives in `cowork_settings.json`, not `installed_plugins.json` —
  without it the plugin installs "Disabled".
- No `.git` required in `installLocation`; Desktop does not re-validate the
  github `source` at load time (proven with a non-existent repo).

Claude Code uses the **identical schema** rooted at `~/.claude/plugins/`.

## Architecture

```
nexty-agent-skills (github)
   │  submodule: external/nexty-agent-skills in nxd monorepo
   ▼
CI (.github/workflows/nxd.cli.yml)
   │  git submodule update --init external/nexty-agent-skills
   │  build skill bundle (reuse build-skills.sh OR raw src/) + write skills/version
   ▼
nxd-cli-installer nginx pod  (EXISTING — components/cli/installer.Dockerfile)
   │  serves  app.<domain>/cli/skills/version        (plain text, like /cli/version)
   │          app.<domain>/cli/skills/bundle.tar.gz  (static)
   ▼
nxd CLI  (components/cli/src/skills.rs — NEW)
   │  nxd skills install [--code|--desktop|--cowork|--all]
   │  nxd skills status | uninstall | update
   │  on startup: skills_version_check()  ── self-heal, mirrors update::version_check
   ▼
Claude Code (~/.claude/plugins) + Desktop/Cowork (local-agent-mode store)
```

Skills served UNDER `/cli/skills/...` → reuses the installer pod's existing
HTTPRoute (`PathPrefix /cli`) with **zero ingress changes**.

## Components

### 1. Submodule + CI

- Add `[submodule "external/nexty-agent-skills"]` to `.gitmodules` (mirror
  `external/nxd-policies`).
- In the installer build workflow (`.github/workflows/nxd.cli.yml`), add
  `git submodule update --init external/nexty-agent-skills` before the bake
  (mirrors `nxd.shared.yml:73`).
- In `components/cli/installer.Dockerfile`: build the skill bundle from the
  submodule and `COPY` it to `/usr/share/nginx/cli/skills/`, plus
  `echo -n $SKILLS_VERSION > /usr/share/nginx/cli/skills/version`
  (mirrors the `version` line at `installer.Dockerfile:34`).
  - `SKILLS_VERSION` = the submodule's `.claude-plugin/plugin.json` version.
  - Bundle = `tar czf` of the skill `src/` (submodule initialized so
    nxd-data-product-builder ships its examples).

### 2. Pod serving (nginx)

- No new `location` block needed if skills live under `/cli/skills/` (the
  existing `autoindex`/static block at `installer/nginx/default.conf:41` covers
  it). Confirm `.tar.gz` + extensionless `version` are served as static.
- Endpoints:
  - `GET /cli/skills/version` → `0.8.0\n`
  - `GET /cli/skills/bundle.tar.gz` → bundle
  - (optional) `GET /cli/skills/bundle.tar.gz.sha256` → checksum

### 3. `nxd skills` subcommand (Rust)

Wiring (per Explore findings):
- `components/cli/src/lib.rs` — add `pub mod skills;`
- `components/cli/src/args.rs` — `Skills { command: skills::SkillsCommand }` in
  the `Command` enum (`args.rs:49`), a dispatch arm in `run()` (`args.rs:167`),
  and a `path()` arm (`args.rs:225`, else debug_assert tests fail).

Model the Claude write-path on `mcp.rs` (`get_claude_config_path()` at
`mcp.rs:285`) — it already does cross-platform Claude Desktop/Code discovery.

Subcommands:
- `nxd skills install [--code|--desktop|--cowork|--all]` — fetch bundle from
  `{get_app_url()}/cli/skills/bundle.tar.gz`, extract, run the marketplace-cache
  inject (port install.sh logic to Rust).
- `nxd skills uninstall [targets]` — reverse the 3-file registration + remove
  cache/marketplace dirs.
- `nxd skills status` — installed/enabled/version per target.
- `nxd skills update` — explicit re-sync (same code path as the silent check).

The on-disk inject logic is a direct port of the proven `install.sh` functions:
`build_plugin_cache` (strip `skills` key), `register_marketplace`,
`register_plugin`, `register_settings` (enable). Mesh URL from `get_app_url()`.

### 4. Auto-sync (the "same as CLI updater" part)

Mirror `update::version_check` (`update.rs:125`) exactly:
- Hook into `lib.rs:169` invocation path, alongside the existing version_check.
- `get_latest_skills_version()` GETs `{get_app_url()}/cli/skills/version`
  (mirror `get_latest_version()` at `update.rs:261`).
- Throttle via a `~/.nxd/skills-version.yaml` timestamp (mirror the 5-min window
  / `cli-version.yaml` at `update.rs:139`).
- Respect the SAME skip switches: `skip_version_check` config /
  `--skip-version-check` / `NXD_CLI_SKIP_VERSION_CHECK`.
- **Self-heal rule:** only act when skills are ALREADY installed (don't
  force-install on opt-out users). If `installed_version < published_version` for
  an installed target → silently re-inject that target. Best-effort: any network
  failure is swallowed, never blocks the actual `nxd` command (15s timeout, same
  as `lib.rs:169`).
- Auth/cadence/failure semantics: inherited from the updater — no new model.

## Cross-mesh / version behavior

Inherited from the updater: the version source is `{active mesh}/cli/skills/version`.
Since this mirrors how the CLI itself updates against the active mesh, skills
track the active mesh's published version the same way the binary does. No
special-case rule beyond what `update.rs` already does. (If multi-cluster skew
becomes a real problem, revisit — not a launch blocker.)

## What's reused vs new

**Reused as-is:** mesh/URL discovery (`config.rs`), `get_app_url()`, the nginx
installer pod + its HTTPRoute, the submodule+CI pattern, the entire
version-check/self-update machinery (`update.rs`), Claude config path discovery
(`mcp.rs`).

**New:** `.gitmodules` entry; a CI submodule-init + bundle step in the installer
Dockerfile; `nxd skills` clap subcommand + Rust port of the inject; a
skills-version-check modeled on `update::version_check`.

**Net: no net-new infra.**

## Phasing

1. **P2a — Rust inject + `nxd skills install/uninstall/status`**, content fetched
   from the pod. (install.sh stays for repo-clone / dev use.)
2. **P2b — CI: submodule + installer Dockerfile bundle + `skills/version`.**
3. **P2c — silent self-heal** (`skills_version_check`) wired into `lib.rs`.

Each phase independently shippable + testable on the local cluster.

## Open questions

1. **Claude Code: marketplace plugin vs loose `~/.claude/skills/`?** Both work.
   Marketplace gives `/plugin` management + grouping + parity with Desktop; loose
   is what install.sh does today. Lean marketplace for consistency.
2. **Bundle granularity** — one `bundle.tar.gz` (simple) vs per-skill (allows
   `--skills` subset fetch). Lean single bundle; `--skills` filters post-extract.

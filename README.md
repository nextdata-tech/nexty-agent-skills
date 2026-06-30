# Nexty AI

## AI-Assisted Development on Nextdata

We have two main paths for AI-assisted data product development. Choose the one that matches your environment.

<table>
<tr>
<td width="50%" align="center" valign="top">

<br>

<b>Nexty AI</b>

<br><br>

**First-party AI coding inside Nextdata OS**

Deep native product context for low code no code experience. Ideal for "zero to one" data product bootstrapping.

</td>
<td width="50%" align="center" valign="top">

<br>

<b>Nexty AI Pro</b>

<br><br>

**Nextdata expertise, in the editor you already use**

Curated by our field engineers. Brings the patterns, skills, and tools your AI assistant needs to build on Nextdata — wherever you're already coding.

<br>

<img src="https://img.shields.io/badge/Claude_Code-D97757?style=flat-square&logo=anthropic&logoColor=white" alt="Claude Code">
<img src="https://img.shields.io/badge/Cursor-000000?style=flat-square&logo=cursor&logoColor=white" alt="Cursor">
<img src="https://img.shields.io/badge/Codex-412991?style=flat-square&logo=openai&logoColor=white" alt="Codex">

<br>


</td>
</tr>
<tr>
<td align="center">

<br>

</td>
<td align="center">

<br>

</td>
</tr>
</table>

---

## What Can I Build?

- **Source-aligned data products** (from S3, ADLS, Snowflake, and Databricks)
- **Aggregate data products** (Quickly build data products from existing data product)
- **Policies** (Quickly build computational policies)

- **Mesh analyzer** (Analyze your existing ETL and data sources and create a plan for packing them as data products)


## Quick Install

From a clone of this repo, the first-party installer handles every Claude target:

```bash
git clone --recurse-submodules https://github.com/nextdata-tech/nexty-agent-skills.git
cd nexty-agent-skills
./scripts/install.sh --code        # Claude Code: copy skills to ~/.claude/skills
./scripts/install.sh --desktop     # Claude Desktop / Cowork: install + enable (no upload)
./scripts/install.sh --all         # all targets
```

`scripts/install.sh` validates the pack (`scripts/validate_skills.py`), initializes the
examples submodule, and installs without any third-party CLI. See
[Installer reference](#installer-scriptsinstallsh) below for targets, scope, and uninstall.

### Alternative: Vercel Skills CLI

```bash
npx skills add nextdata-tech/nexty-agent-skills --all -y
```

The [Vercel Skills CLI](https://github.com/vercel-labs/skills) installs skills to the right
location for each agent automatically. On Windows PowerShell, run the same command.

### Claude Code plugin distribution

This repository also includes Claude Code plugin metadata:

- `.claude-plugin/plugin.json` describes the plugin itself.
- `.claude-plugin/marketplace.json` describes a small marketplace named `nexty`.
- `src/` remains the source of truth for the skills loaded by the plugin.

Use this path when you want customers or field engineers to install the whole Nexty skill pack through Claude Code's plugin flow instead of copying individual skill folders.

#### Own marketplace

This is the lowest-friction customer-sharing option. The marketplace lives in this repository, so users can add this repo as a Claude Code marketplace and install the plugin from it:

```
/plugin marketplace add nextdata-tech/nexty-agent-skills
/plugin install nexty-agent-skills@nexty
```

To iterate on a local checkout, point Claude Code at your clone instead:

```
/plugin marketplace add ./path/to/nexty-agent-skills
/plugin install nexty-agent-skills@nexty
```

Before sharing marketplace install instructions with a customer, validate the plugin:

```bash
claude plugin validate . --strict
```

Keep the plugin self-contained. Do not require files outside this repository path, and do not include customer-specific artifacts, private evals, local credentials, or generated data product outputs in the marketplace package.

#### Community marketplace

The Anthropic community marketplace is a future distribution step, not required for private customer sharing. Use it only after the pack is stable enough for broader public discovery.

Before submitting to the community marketplace:

- Make the repository public or otherwise accessible for review.
- Keep `.claude-plugin/plugin.json` and `.claude-plugin/marketplace.json` valid.
- Run `claude plugin validate . --strict` and fix every warning/error.
- Confirm all skills are agent-neutral, customer-safe, and free of private customer names, secrets, internal URLs, or scenario-specific artifacts.
- Keep private evals under `evals/private/`; do not publish any customer names, schemas, transcripts, or commercial-demo artifacts.
- Include clear install, usage, uninstall, validation, and support instructions in this README.
- Treat community listing as a reviewed submission: Anthropic may reject plugins that fail validation, include unsafe behavior, or are not self-contained.

The official Anthropic & Partners directory is separate from the community marketplace and should be treated as a later partner/curation conversation.

### Installer (`scripts/install.sh`)

The first-party installer is the canonical path. It is pure bash + `python3` (no `npx`,
no `jq`), validates the pack before installing, and supports a clean uninstall.

```bash
scripts/install.sh [install|uninstall|status|help] [targets] [scope] [options]
```

**Targets** (default `--code`): `--code` `--desktop` `--cowork` `--all`.

| Target | What it does |
|--------|--------------|
| `--code` | Copies each skill to `~/.claude/skills/<skill>/` (global) or `./.claude/skills/` with `--project`. Full submodule, no size cap. Idempotent (`rsync --delete`). |
| `--desktop` / `--cowork` | Both are "local-agent-mode". Installs the pack as a local marketplace plugin and enables it — no manual upload. Restart Claude Desktop to load it. `--zip` switches to the build-zip + manual-upload fallback. macOS only. |

**Scope** (Claude Code only): default global `~/.claude/skills`; `--project` → `./.claude/skills`.

**Examples**

```bash
scripts/install.sh --code                       # global Claude Code install (default)
scripts/install.sh --code --project             # current project only
scripts/install.sh --code --skills "nxd-setup nxd-data-product-builder"
scripts/install.sh --desktop                    # install + enable for Desktop/Cowork (then restart)
scripts/install.sh --desktop --zip              # build zips + manual-upload fallback
scripts/install.sh --all                        # every target
scripts/install.sh status --code                # show what's installed
scripts/install.sh uninstall --desktop          # remove + disable the Desktop/Cowork plugin
scripts/install.sh --code --dry-run             # print actions, change nothing
```

Other options: `--no-validate`, `--no-submodule`, `--account-id ID`, `--device-id ID`,
`-y/--yes`, `--verbose`.

#### How the Claude Desktop / Cowork install works

Desktop and Cowork ("local-agent-mode") load plugins from a local marketplace store
under `~/Library/Application Support/Claude/local-agent-mode-sessions/<accountId>/<deviceId>/`.
The installer mirrors what the **Browse plugins** UI writes to disk — it materializes a
marketplace checkout and a plugin cache, then registers the plugin across
`known_marketplaces.json`, `installed_plugins.json`, and `cowork_settings.json`
(which carries the `enabledPlugins` flag, so the plugin installs **enabled**, not disabled).
Every file is backed up before it's edited, and `uninstall --desktop` reverses all of it.
Restart Claude Desktop after installing for it to pick up the change. macOS only;
use `--zip` for the manual-upload fallback.

### Manual install

```bash
git clone --recurse-submodules https://github.com/nextdata-tech/nexty-agent-skills.git
mkdir -p .claude/skills
cp -R nexty-agent-skills/src/* .claude/skills/
```

### Local development on skills

To install from a local checkout for fast iteration:

```bash
npx skills add ./src --all -y
```

This installs skills from the `src/` directory in your working copy. After editing a SKILL.md, re-run the command to update.

To remove and reinstall cleanly:

```bash
npx skills remove --all -y
rm -rf .agents .claude/skills skills-lock.json
npx skills add ./src --all -y
```

or one line:

```bash
npx skills remove --all -y; rm -rf .agents .claude/skills skills-lock.json; npx skills add ./src --all -y
```

## Uninstall

With the first-party installer:

```bash
scripts/install.sh uninstall --code     # or --desktop --rpm-experimental, --all
```

Or, if you installed via the Vercel Skills CLI:

```bash
npx skills remove --all -y
rm -rf .agents .claude/skills skills-lock.json
```

## Available Skills

| Skill | Description |
|-------|-------------|
| `nxd-setup` | Install, configure, and authenticate the nxd CLI |
| `nxd-data-product-builder` | Create, bootstrap, scaffold, refine, and validate a Nextdata OS Python data product — interactive interview or spec-from-document (replaces the former `nexty-bootstrap` wizard) |
| `nxd-adding-inputs` | Add or repair inputs, input semantic models, transform parameters, and input expectations |
| `nxd-adding-outputs` | Add or repair output models, output ports, storage mappings, transform output parameters, and output promises |
| `nxd-adding-expectations-promises` | Add or repair input expectations and output promises |
| `nxd-adding-policy` | Add contracts and activate computational policies with current CLI syntax |
| `nxd-complying-with-failing-policy` | Diagnose policy violations and update the data product to comply |
| `nxd-debugging-data-products` | Diagnose failed data products from describe/logs/init logs/verify output |
| `nxd-data-product-query` | Query a deployed data product — discovery via the MCP gateway; reads via SQL / file fetch / vector similarity / MCP-RPC (REST only for credential leasing) |
| `nxd-mesh-analyzer` | Inspect an infra profile's data-bearing services (S3, Snowflake, ADLS, BigQuery, Postgres, Kafka, …) read-only and report candidate data product inputs/outputs grouped by domain |
| `nxd-policies` | List, activate, and deactivate computational policies on a data product via the nxd CLI |
| `nxd-semantic-data-product` | Build a governed text-to-SQL / semantic-layer data product that exposes curated metrics and dimensions over MCP, so an AI agent can answer natural-language questions without writing raw SQL |

## Usage

Start Claude Code in any project and invoke a skill:

```
/nxd-setup                  # Set up the nxd CLI
/nxd-data-product-builder   # Build / bootstrap a new data product
/nxd-adding-inputs          # Add inputs to an existing data product
/nxd-adding-outputs         # Add output ports and promises
/nxd-debugging-data-products # Debug a failed deployed data product
/nxd-data-product-query     # Query output ports from deployed data products
/nxd-mesh-analyzer          # Discover candidate data products from an infra profile
/nxd-policies               # List, activate, and deactivate policies
```

Skills also activate automatically — just ask "bootstrap a new data product" and the agent will use the right skill.

## Tutorial: Build a Data Product

Use this tutorial to test whether the skills can help an agent build a Nextdata OS data product from a requirement. The same skill pack can be used from Claude Code or Claude Desktop, but the output behavior is different.

| Interface | Best for | Output location |
|-----------|----------|-----------------|
| Claude Code | Real implementation work, terminal checks, `nxd validate`, repo commits | Real files in the current terminal directory |
| Claude Desktop | Reviewing the workflow, producing downloadable starter files, demos without terminal setup | Usually downloadable artifacts from the chat |

If you need a real project folder that you can inspect with `ls`, commit to git, and validate with `nxd`, use Claude Code.

### Claude Code path

Claude Code is the recommended path for a real data product build because it starts in a local working directory and can create files, inspect them, and run safe validation commands.

You can use Claude Code in two ways:

- **Claude Code CLI:** run `claude` from a terminal.
- **Claude Code VS Code extension:** open the Claude Code panel inside VS Code.

If `claude` returns `command not found`, you have the VS Code extension but not the CLI binary on your shell `PATH`. Either install the CLI or use the VS Code extension flow below.

#### 1. Check or install Claude Code CLI

If you want to use the terminal flow, first check whether the CLI is installed:

```bash
command -v claude
claude --version
```

If it is missing, install Claude Code with one of the official install options:

```bash
# macOS, Linux, or WSL
curl -fsSL https://claude.ai/install.sh | bash

# macOS Homebrew alternative
brew install --cask claude-code

# npm alternative; do not use sudo
npm install -g @anthropic-ai/claude-code
```

Restart your terminal after installing, then run:

```bash
claude
```

The first launch prompts you to log in.

#### 2. Update the skill pack

```bash
cd ~/src/nexty-agent-skills
git pull --ff-only
python3 scripts/validate_skills.py
./build-skills.sh
npx skills add ./src -g -a claude-code -s '*' -y
```

You should see output similar to:

```text
Found 11 skills
Installed 11 skills
```

The `-g` flag installs the skills globally for your user, so Claude Code can use them from any project directory. The `-a claude-code` flag targets Claude Code only. If you use `--all -g`, the Skills CLI may also try agents that do not support global installs and print unrelated failures such as `PromptScript does not support global skill installation`.

#### 3. Start Claude Code from the target project directory

##### Option A: terminal CLI

```bash
mkdir -p ~/src/jira-issues-dp-test
cd ~/src/jira-issues-dp-test
claude
```

Everything Claude builds should now be written under:

```text
~/src/jira-issues-dp-test
```

##### Option B: VS Code extension

If you only have the VS Code extension:

```bash
mkdir -p ~/src/jira-issues-dp-test
code ~/src/jira-issues-dp-test
```

If `code` is not available on your shell `PATH`, open VS Code manually and choose `File > Open Folder...`, then select `~/src/jira-issues-dp-test`.

Then in VS Code:

1. Open the Claude Code panel with the Spark icon, or press `Cmd+Shift+P` and search for `Claude Code`.
2. Start a new Claude Code conversation from that workspace.
3. Use the same prompt below.

Claude should treat the opened VS Code folder as the project workspace. Ask it to state the exact project directory before writing files.

#### 4. Ask Claude Code to build from the example requirement

Paste this prompt into the new Claude Code conversation:

```text
Use the Nexty skills to build a Nextdata OS Python data product from this requirement:

~/src/nexty-agent-skills/example-input/jira-data-product.md

Use nxd-data-product-builder as the main skill. Use supporting workflow skills when needed:
- nxd-setup
- nxd-adding-inputs
- nxd-adding-outputs
- nxd-adding-expectations-promises
- nxd-debugging-data-products

Important:
- Build inside the current directory.
- Before writing code, state the exact project directory.
- Do not use Claude Desktop artifacts; write real files to disk.
- Do not use demo mesh values unless I explicitly confirm them.
- Do not launch anything.
- Do not create runtime resources unless I explicitly approve.
- Create README.md with a Build Status table.
- Create REQUIREMENTS_CHECKLIST.md.
- Run generated-code preflight before handoff.
- Run safe local checks.
- Run the offline spec-build check with `data_product_spec_from_file_at_path(...)`.
- Run nxd validate only if nxd is configured and available.
- When running nxd validate, capture the command output and exit code, then summarize PASS, FAIL, or NOT RUN.
- If nxd validate cannot run, mark it as NOT RUN with the exact blocker and command to run next.
```

To use a customer requirement instead, replace the example file path with the pasted requirement text or with the path to the customer's requirement document.

On Windows PowerShell, use the same flow with Windows paths:

```powershell
cd $HOME\src\nexty-agent-skills
git pull --ff-only
python scripts\validate_skills.py
bash ./build-skills.sh
npx skills add ./src -g -a claude-code -s '*' -y

New-Item -ItemType Directory -Force $HOME\src\jira-issues-dp-test
cd $HOME\src\jira-issues-dp-test
claude
```

`build-skills.sh` is a Bash script, so Windows users should run it from WSL, Git Bash, or PowerShell with `bash` available.

#### 5. Verify what was built

After Claude finishes, check the real local folder:

```bash
pwd
ls -la
```

Expected starter files usually include:

```text
spec.py
models.py
transform.py
README.md
REQUIREMENTS_CHECKLIST.md
requirements.txt
pyproject.toml
.nxdignore
```

The generated `README.md` should clearly show:

- the project directory,
- whether files were created on disk,
- which local tests passed,
- whether `nxd validate` passed, failed, or was not run, including the exit code if it ran,
- whether anything was launched,
- the remaining TODOs before launch.

If `nxd validate` was not run, the README must include the exact blocker and the next command to run.

### Claude Desktop path

Claude Desktop is useful for testing the skill behavior and generating downloadable starter artifacts. It is not the cleanest path for proving a data product was built in a local folder, because Desktop conversations often return files as artifacts/downloads instead of writing into your terminal's current directory.

#### 1. Build the ZIP files

```bash
cd ~/src/nexty-agent-skills
git pull --ff-only
python3 scripts/validate_skills.py
./build-skills.sh
```

This creates one ZIP per skill at the repository root, for example:

```text
nxd-data-product-builder.zip
nxd-setup.zip
nxd-adding-inputs.zip
nxd-adding-outputs.zip
nxd-adding-expectations-promises.zip
nxd-debugging-data-products.zip
```

#### 2. Install the ZIPs in Claude Desktop

Claude Desktop does not use `npx skills add ./src --all -y` for this flow. Install the generated ZIP files through the Desktop UI.

In Claude Desktop:

1. Open `Customize`.
2. Open `Skills`.
3. Click `+`.
4. Choose `Create skill`.
5. Choose `Upload a skill`.
6. Upload each `nxd-*.zip` file you want to test.
7. Confirm the skills are enabled.

For a full data product build test, install at least:

- `nxd-data-product-builder.zip`
- `nxd-setup.zip`
- `nxd-adding-inputs.zip`
- `nxd-adding-outputs.zip`
- `nxd-adding-expectations-promises.zip`
- `nxd-debugging-data-products.zip`

If your organization uses Team or Enterprise skill provisioning, an admin can upload the ZIPs once through organization settings instead of every user uploading them individually.

#### 3. Start a new Claude Desktop chat

Attach or paste the requirement. For the bundled smoke test, use:

```text
example-input/jira-data-product.md
```

Then paste this prompt:

```text
Use the Nexty skills to build a Nextdata OS Python data product from the attached requirement.

Use nxd-data-product-builder as the main skill. Use supporting workflow skills when needed:
- nxd-setup
- nxd-adding-inputs
- nxd-adding-outputs
- nxd-adding-expectations-promises
- nxd-debugging-data-products

Important:
- If you cannot write to a real local filesystem path, say that clearly before generating files.
- If you produce downloadable artifacts, state: "Local filesystem path: Not created until Download all."
- Do not claim the data product was built in a local directory unless you actually created files there.
- Do not use demo mesh values unless I explicitly confirm them.
- Do not launch anything.
- Do not create runtime resources unless I explicitly approve.
- Create README.md with a Build Status table.
- Create REQUIREMENTS_CHECKLIST.md.
- Run generated-code preflight before handoff.
- Run only safe local checks available in this chat environment.
- Run the offline spec-build check if the local nxd package is available.
- Mark nxd validate as PASS, FAIL, or NOT RUN.
- If nxd validate runs, include the exit code and the first actionable error, if any.
- If nxd validate cannot run, include the exact blocker and command to run next.
```

#### 4. Download and inspect artifacts

If Claude Desktop returns downloadable files, click `Download all` and unzip them into a local project folder, for example:

```bash
mkdir -p ~/src/jira-issues-dp-test
cd ~/src/jira-issues-dp-test
# unzip or move the downloaded files here
ls -la
```

Then inspect `README.md` and `REQUIREMENTS_CHECKLIST.md` before running any launch command.

#### 5. Validate locally after download

Once the files are in a real local folder, run safe checks yourself:

```bash
python3 -m compileall .
```

If `nxd` is configured and the generated README says TODOs are resolved, run:

```bash
nxd --config=<session_config> whoami
nxd validate --config=<session_config> . --debug
echo "nxd validate exit code: $?"
```

If `--debug` output is noisy or has no final success line, run the same command
again without `--debug` and check the exit code. Treat validation as PASS only
when auth is confirmed, the validate command exits `0`, and no validation error
or traceback is printed.

Only run launch after validation passes and a human approves it:

```bash
nxd launch --dir . --config=<session_config>
```

### Expected status language

Every generated data product handoff should distinguish these states:

- **Built locally:** source files exist in a real filesystem directory.
- **Generated as artifacts:** files exist only as downloadable chat artifacts until downloaded.
- **Validated:** `nxd validate` actually ran and passed.
- **Not validated:** `nxd validate` did not run; the blocker and next command are documented.
- **Launched:** `nxd launch` actually ran.
- **Not launched:** no runtime resources were created.

Do not treat generated source files as a deployed data product. A data product is not running on a mesh until it has been validated, launched, and confirmed in the target environment.

## Adding a New Skill

1. Create a directory under `src/<skill-name>/`
2. Add a `SKILL.md` with YAML frontmatter:
3. Add reference docs in `reference/` if needed
4. Test locally with `npx skills add ./src --all -y`

### Conventions

These are enforced by `scripts/validate_skills.py` in CI (`.github/workflows/ci.yml`). A skill fails the build unless:

- Skill names: lowercase, hyphens only, 1-64 chars, and the `name:` field **must match the directory name**
- Descriptions must be specific, stay under 1024 characters, include a clear `Use when ...` trigger clause, and contain **no angle-bracket placeholders** (e.g. `<DP>`)
- `allowed-tools` must be present and non-empty, listing only known Claude Code tools (`Bash`, `Read`, `Write`, `Edit`, `MultiEdit`, `Glob`, `Grep`, `AskUserQuestion`, `Agent`, `Task`, `TodoWrite`, `WebFetch`, `WebSearch`, `NotebookEdit`)
- `metadata.version`, if set, must be semver (`X.Y.Z`)
- Keep `SKILL.md` under 500 lines for context efficiency
- Move detailed references to `reference/` (singular only — `references/` is rejected) for progressive disclosure
- Add a `## Contents` section near the top of reference files longer than 100 lines
- Each skill zip stays under the 200-entry Claude Desktop cap (enforced via `build-skills.sh` in CI)
- Run `python3 scripts/validate_skills.py` and `./build-skills.sh` before sharing updated ZIPs

### Claude Desktop packaging limits

Claude Desktop rejects skills that violate either of these. Use `./build-skills.sh` to package; it strips noise and reports per-skill file counts.

- **Max 200 entries per skill zip.** Counts files + directory entries. The build script passes `zip -D` to drop empty dir entries and excludes VCS/caches/lockfiles/OS junk. If a bundled examples repo pushes you over, strip per-DP housekeeping (`README.md`, `.python-version`, `pyproject.toml`, `notebooks/`, `tests/`) before code.
- **No XML / angle-bracket tags in the SKILL.md `description` field.** Placeholders like `<DP>` or `<table>` in the frontmatter description trip the loader. Use plain wording (`a named DP`, `the table`) instead. Body content is fine; only the YAML frontmatter `description:` is parsed strictly.

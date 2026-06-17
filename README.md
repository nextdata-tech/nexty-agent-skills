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

```bash
npx skills add nextdata-tech/nexty-agent-skills --all -y
```

The [Vercel Skills CLI](https://github.com/vercel-labs/skills) installs skills to the right location for each agent automatically.

For Windows PowerShell, run the same command in PowerShell:

```powershell
npx skills add nextdata-tech/nexty-agent-skills --all -y
```

### Claude Code plugin

Install all skills as a Claude Code plugin:

```
/plugin marketplace add nextdata-tech/nexty-agent-skills
/plugin install nexty-agent-skills@nexty
```

To iterate on a local checkout, point the marketplace at your clone instead:

```
/plugin marketplace add ./path/to/nexty-agent-skills
/plugin install nexty-agent-skills@nexty
```

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
| `nxd-data-product-query` | Query a deployed data product's output ports (SQL, file fetch, vector similarity, or MCP/RPC) via its REST API |
| `nxd-mesh-analyzer` | Inspect an infra profile's data-bearing services (S3, Snowflake, ADLS, BigQuery, Postgres, Kafka, …) read-only and report candidate data product inputs/outputs grouped by domain |
| `nxd-policies` | List, activate, and deactivate computational policies on a data product via the nxd CLI |

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

## Adding a New Skill

1. Create a directory under `src/<skill-name>/`
2. Add a `SKILL.md` with YAML frontmatter:
3. Add reference docs in `references/` if needed
4. Test locally with `npx skills add ./src --all -y`

### Conventions

- Skill names: lowercase, hyphens only, 1-64 chars
- Descriptions must be specific, stay under 1024 characters, and include a clear `Use when ...` trigger clause
- Keep `SKILL.md` under 500 lines for context efficiency
- Move detailed references to `reference/` or `references/` for progressive disclosure
- Add a `## Contents` section near the top of reference files longer than 100 lines
- Run `python3 scripts/validate_skills.py` and `./build-skills.sh` before sharing updated ZIPs

### Claude Desktop packaging limits

Claude Desktop rejects skills that violate either of these. Use `./build-skills.sh` to package; it strips noise and reports per-skill file counts.

- **Max 200 entries per skill zip.** Counts files + directory entries. The build script passes `zip -D` to drop empty dir entries and excludes VCS/caches/lockfiles/OS junk. If a bundled examples repo pushes you over, strip per-DP housekeeping (`README.md`, `.python-version`, `pyproject.toml`, `notebooks/`, `tests/`) before code.
- **No XML / angle-bracket tags in the SKILL.md `description` field.** Placeholders like `<DP>` or `<table>` in the frontmatter description trip the loader. Use plain wording (`a named DP`, `the table`) instead. Body content is fine; only the YAML frontmatter `description:` is parsed strictly.

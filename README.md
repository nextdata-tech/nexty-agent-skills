# nextdata Agent Skills

AI agent skills for building data products on the [nextdata](https://nextdata.com) platform. Built on the open [Agent Skills](https://agentskills.io) specification.

## Quick Install

```bash
npx skills add nextdata-tech/nexty-agent-skills --all -y
```

The [Vercel Skills CLI](https://github.com/vercel-labs/skills) installs skills to the right location for each agent automatically.

### Manual install

```bash
git clone https://github.com/nextdata-tech/nexty-agent-skills.git
mkdir -p .claude/skills
cp -r nexty-agent-skills/src/nxd-setup .claude/skills/nxd-setup
cp -r nexty-agent-skills/src/nexty-bootstrap .claude/skills/nexty-bootstrap
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

## Uninstall

```bash
npx skills remove --all -y
rm -rf .agents .claude/skills skills-lock.json
```

## Available Skills

| Skill | Description |
|-------|-------------|
| `nxd-setup` | Install, configure, and authenticate the nxd CLI |
| `nexty-bootstrap` | Interactive wizard to bootstrap a new nextdata data product |

## Usage

Start Claude Code in any project and invoke a skill:

```
/nxd-setup              # Set up the nxd CLI
/nexty-bootstrap        # Bootstrap a new data product
```

Skills also activate automatically — just ask "bootstrap a new data product" and the agent will use the right skill.

## Adding a New Skill

1. Create a directory under `src/<skill-name>/`
2. Add a `SKILL.md` with YAML frontmatter:
3. Add reference docs in `references/` if needed
4. Test locally with `npx skills add ./src --all -y`

### Conventions

- Skill names: lowercase, hyphens only, 1-64 chars
- Keep SKILL.md under 500 lines for context efficiency
- Move detailed references to `references/` for progressive disclosure

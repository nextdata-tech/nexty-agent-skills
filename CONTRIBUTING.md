# Contributing to nextdata Agent Skills

## Local Development Setup

Symlink skills into your Claude Code skills directory so edits are picked up immediately:

```bash
# Clone the repo
git clone https://github.com/nextdata-tech/nexty-agent-skills.git
cd nexty-agent-skills

# Symlink each skill you're working on
ln -s "$(pwd)/skills/nextdata/nxd-setup" ~/.claude/skills/nxd-setup
ln -s "$(pwd)/skills/nextdata/nexty-bootstrap" ~/.claude/skills/nexty-bootstrap
```

Start Claude Code and test with `/nexty-bootstrap`. Edits to `SKILL.md` are picked up on the next conversation — no restart needed.

## Adding a New Skill

1. Create a directory under `skills/nextdata/<skill-name>/`
2. Add a `SKILL.md` with YAML frontmatter:

```yaml
---
name: my-skill
description: What the skill does and when to use it.
---

# My Skill

Instructions for the agent...
```

3. Add reference docs in `references/` if needed
4. Test locally via symlink (see above)

## Directory Structure

```
skills/nextdata/<skill-name>/
├── SKILL.md              # Required: skill definition with frontmatter
├── references/           # Optional: detailed docs for progressive loading
├── scripts/              # Optional: executable scripts
└── assets/               # Optional: templates, resources
```

## Conventions

- Skill names: lowercase, hyphens only, 1-64 chars
- Keep SKILL.md under 500 lines for context efficiency
- Move detailed references to `references/` for progressive disclosure

# nextdata Agent Skills

AI agent skills for building data products on the [nextdata](https://nextdata.com) platform. Built on the open [Agent Skills](https://agentskills.io) specification.

## Install

### Claude Code

```bash
npx skills add nextdata-tech/nexty-skills
```

### OpenAI Codex

```bash
npx skills add nextdata-tech/nexty-skills
```

The [Vercel Skills CLI](https://github.com/vercel-labs/skills) installs skills to the right location for each agent automatically.

### Manual install

```bash
git clone https://github.com/nextdata-tech/nexty-skills.git
mkdir -p ~/.claude/skills
cp -r nexty-skills/skills/nextdata/nxd-setup ~/.claude/skills/nxd-setup
cp -r nexty-skills/skills/nextdata/nexty-bootstrap ~/.claude/skills/nexty-bootstrap
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

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for how to develop and test skills locally.

## License

Apache 2.0

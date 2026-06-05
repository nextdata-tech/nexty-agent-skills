# argenx EDP Tutorial — Claude plugin (experimental)

A **separate, experimental Claude plugin** that turns the argenx "0 → data product" walkthrough
into a **guided, agent-led tutorial in educational mode** — built for **Cowork** and for
first-time users who have never opened a terminal.

> Experimental spike for the argenx sandbox kickoff. The goal: make building the first data
> product feel *easy* for a post-technical user on a locked-down Windows VDI, so they're
> comfortable greenlighting the project.

## What it is

One skill, `argenx-edp-tutorial`, that walks a learner from zero to a deployed data product:

0. **Meet the learner** — calibrate pace/language to their comfort level and real goal.
1. Make sure the tools are ready (`uv`, `nxd`, mesh connection).
2. Create the project folder.
3. Scaffold from the **published argenx template** (EDP library comes with it — nothing to clone).
4. Write the spec, one explained block at a time.
5. Write a trivial transform (end-to-end success before real logic).
6. `nxd validate` → `nxd launch` 🚀 — then celebrate.
7. Tailored next step — explore the advanced reference DP, **or** build their real **Alation
   reference DP** (Alation API → ingestion → Snowflake → shareable reference) as a guided diff.

## Design choices (why it differs from `nexty-bootstrap`)

- **Educational, not practitioner.** Existing skills assume CLI fluency; this assumes none.
  One step at a time, "why before how", jargon defined just-in-time, progress celebrated.
- **Cowork-first.** The agent runs commands and shows results; the learner only acts when only
  they can (browser login, Azure consent).
- **argenx-VDI-real.** Native `nxd.exe` is blocked by AppLocker on the customer VDI — the skill
  routes to **WSL** as *the* path, not a footnote. (Per Diego's env findings.)
- **Only user-facing surfaces.** References point to platform docs + nxd CLI / REST API / MCP
  tools — nothing the learner can't actually reach (no internal repos).
- **Generic now, Alation-ready.** The spine is the proven NEX-582 walkthrough; the Alation
  swap is a guided final step on top of what they already understand.

## Layout

```
argenx-tutorial-plugin/
├── .claude-plugin/
│   ├── plugin.json          # plugin manifest (skills: ./skills/)
│   └── marketplace.json     # marketplace manifest ("argenx")
└── skills/argenx-edp-tutorial/
    ├── SKILL.md             # the guided flow (lean; detail offloaded to references/)
    └── references/          # loaded on demand
        ├── templates.md         # exact pyproject/spec/transform + walkthroughs
        ├── glossary.md          # plain-language term definitions
        ├── windows-wsl.md       # AppLocker block → WSL path, PATH/CRLF snags
        ├── links.md             # canonical platform doc links only
        ├── troubleshooting.md   # uv sync / validate / launch errors
        ├── setup-fallback.md    # when nxd-setup absent; CLI/REST discovery
        └── alation-target.md    # tailoring toward the Alation reference DP
```

## Try it locally

```
/plugin marketplace add ./argenx-tutorial-plugin
/plugin install argenx-edp-tutorial@argenx
```

Then in any project: `/argenx-edp-tutorial`, or just say *"help me build my first argenx data
product step by step."*

## Status / open questions

- Spine verified against the NEX-582 README and the `salesforce_snowpipe_adls_to_snowflake`
  reference DP. **Not yet run end-to-end against a live argenx mesh** — needs a real run on the
  sandbox to confirm template name, registry URL, and doc paths.
- Alation specifics (service name, ingestion API surface, object schemas) are placeholders to
  fill from the live infra profile.
- Could fold into `nexty-agent-skills` as a skill, or stay a standalone "argenx skills" plugin
  (Sina's framing). Kept separate for now per that direction.

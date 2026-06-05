# Connect the data product to Claude Desktop (MCP)

The payoff step: once the learner has a deployed data product that exposes an **MCP port**,
wire it into **Claude Desktop** so they can ask questions about their data in plain language.
This is the "wow" moment — they go from "I built a pipeline" to "I'm talking to my data."

The nxd CLI does this for you: `nxd mcp config` generates the MCP server entry and can write it
straight into Claude Desktop's config. **But the argenx VDI runs the CLI in WSL while Claude
Desktop runs on Windows**, and that split needs care — see the WSL section below.

## What `nxd mcp config` does

```bash
nxd mcp config --target claude --write
```

- `--target claude` → Claude Desktop (`--target claude-code` targets the Claude Code CLI instead)
- generates an `mcpServers` entry named `nxd-<env>` (e.g. `nxd-demo`)
- the entry runs a small **stdio bridge** (`nxd mcp client --base-url <dp-url> --token <pat>`) that
  proxies Claude Desktop to your remote data product's MCP port
- `--write` merges it into Claude Desktop's `claude_desktop_config.json` (creates the file/dir if
  missing, dedupes by server name, asks before overwriting an existing one)
- needs a **PAT**: it uses the one in your CLI config, or offers to generate a 30-day one, or use
  `--personal-access-token <pat>`. (`--no-pat` writes a `<NXD_PAT>` placeholder to fill later.)

Without `--write` it prints the JSON so you can inspect or place it yourself. You can also target
an explicit file with `--output <path>` (also merges if the file exists).

Config locations the CLI uses for `--write` (native, per-OS):
- **macOS:** `~/Library/Application Support/Claude/claude_desktop_config.json`
- **Windows:** `%APPDATA%\Claude\claude_desktop_config.json`
- **Linux:** `~/.config/Claude/claude_desktop_config.json`

## ⚠️ WSL ↔ Windows Desktop: the cross-boundary catch

On the argenx VDI the CLI runs in **WSL (Linux)** but **Claude Desktop is a Windows app.** A plain
`nxd mcp config --target claude --write` from inside WSL does the *Linux* thing:

1. it writes to the **Linux** config path (`~/.config/Claude/...`) — which the **Windows** Desktop
   never reads (Windows Desktop reads `%APPDATA%\Claude\claude_desktop_config.json`), and
2. it sets the bridge `command` to the **Linux** `nxd` binary path — which a **Windows** process
   can't launch directly.

So `--write` from WSL silently wires up nothing usable. Handle it one of two ways:

### Option A (recommended) — generate in WSL, run the bridge through `wsl.exe`

Generate the entry but don't let it write the Linux config; print it, then place a Windows-correct
version in the Windows config. The trick: make the `command` `wsl.exe` so Windows Desktop launches
the WSL bridge.

1. In WSL, get the data-product URL and a PAT, and preview the entry:
   ```bash
   nxd mcp config --target claude          # prints the JSON; note the base-url and token
   ```
2. Write `%APPDATA%\Claude\claude_desktop_config.json` (Windows side) with an entry whose command
   crosses into WSL. Shape:
   ```json
   {
     "mcpServers": {
       "nxd-<env>": {
         "command": "wsl.exe",
         "args": [
           "nxd", "--skip-version-check", "mcp", "client",
           "--base-url", "<dp-url>",
           "--token", "<pat>"
         ]
       }
     }
   }
   ```
   You can reach the Windows config from WSL at
   `/mnt/c/Users/<user>/AppData/Roaming/Claude/claude_desktop_config.json` — read it, merge the
   `nxd-<env>` key (don't clobber other servers), write it back. Confirm `wsl.exe nxd` resolves
   (i.e. `nxd` is on PATH inside the default WSL distro); if not, use the absolute Linux path:
   `"args": ["-e", "/home/<user>/.local/bin/nxd", "--skip-version-check", "mcp", "client", ...]`.
3. Restart Claude Desktop.

### Option B — run the whole CLI natively on Windows

Only viable if AppLocker is *not* blocking `nxd.exe` (it is, on the known argenx VDI — see
`windows-wsl.md`). If a future environment allows native execution, `nxd mcp config --target
claude --write` from a Windows shell just works, no bridge gymnastics. Default to Option A on the
locked-down VDI.

## After wiring it

1. **Restart Claude Desktop** (it only reads the config at startup).
2. In Desktop, confirm the `nxd-<env>` server appears and its tools are listed.
3. Have the learner ask a question that hits one of the product's MCP tools (e.g. "list the
   regions in my data product" / "get the record with id …"). Seeing Desktop answer *from data
   they just deployed* is the moment that sells it.

## Teaching notes

- Explain plainly: *"MCP is how Claude Desktop talks to outside tools. We're registering your data
  product as one of those tools, so you can just ask Desktop about your data."*
- The PAT is a key — treat it like a password, it's going into a local config file. The
  auto-generated one expires in 30 days; that's fine for a demo.
- If Desktop doesn't show the server: 90% of the time it's (a) didn't restart, or (b) the WSL
  cross-boundary issue above — re-check the `command` is `wsl.exe`, not a bare Linux path.

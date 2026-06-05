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

## ⚠️ The core problem: Desktop is on Windows, the CLI isn't runnable there

This is the hardest part of the whole tutorial on the argenx VDI, and it's worth understanding
before touching config. Claude Desktop runs as a **Windows** app, so its MCP server entry must be
a command **Windows can launch**. But the bridge that connects to the data product is the
`nxd` CLI — and **native `nxd.exe` is AppLocker-blocked on Windows** (see `windows-wsl.md`). The
working CLI lives in **WSL (Linux)**. So Desktop-on-Windows can't just call `nxd` directly.

That mismatch breaks the naive command in two ways. A plain `nxd mcp config --target claude
--write` run *inside WSL* does the *Linux* thing:

1. it writes the **Linux** config path (`~/.config/Claude/...`) — which the **Windows** Desktop
   never reads (Windows Desktop reads `%APPDATA%\Claude\claude_desktop_config.json`), and
2. it sets the bridge `command` to the **Linux** `nxd` binary path — which a **Windows** process
   can't launch.

So `--write` from WSL silently wires up nothing usable. There are three ways through, in order of
preference. **All of them need verifying on the actual VDI** — the same IT controls that block
`nxd.exe` (AppLocker, and the **antivirus** the team has hit on these VDIs) may also restrict
`wsl.exe` spawning or Python execution. Try A; if it's blocked, fall back to B (Python script);
C is only for an unlocked environment.

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

### Option B — Python proxy-bridge fallback (no `nxd.exe` at all)

Use this when Option A doesn't work — e.g. Desktop can't spawn `wsl.exe`, or WSL isn't available,
but **Python is available on Windows** (often the case even where the CLI is blocked). The bridge
the CLI runs is just a small **stdio ↔ streamable-HTTP MCP proxy**: it speaks MCP over stdio to
Claude Desktop and forwards to the data product's remote MCP endpoint at `<base-url>` with the
`x-nextdata-token: <pat>` header. That's reproducible as a standalone Python script — the field
team has used an older Python proxy script for exactly this (connecting to the MCP gateway without
the CLI).

Wiring shape — point Desktop at the Python script directly:
```json
{
  "mcpServers": {
    "nxd-<env>": {
      "command": "python",
      "args": [
        "C:\\path\\to\\nxd_mcp_proxy.py",
        "--base-url", "<dp-url>",
        "--token", "<pat>"
      ]
    }
  }
}
```

- **Get the script from the field team**, don't reconstruct it from scratch — ask where the
  argenx/Nextdata MCP Python proxy lives (it has been kept under a `mcp_tools/nxd_mcp`-style
  path). Confirm it targets *this* environment's base URL.
- The script needs its Python deps available to whatever `python` Desktop launches (a venv or a
  global install). If Python isn't on Windows either, this option is out — fall back to A, or get
  IT to whitelist one of the binaries.
- This path **avoids `nxd.exe` and `wsl.exe` entirely**, which is why it survives the strictest
  AppLocker setups — but the antivirus on the VDI can still quarantine an unsigned `.py` or block
  outbound HTTPS; verify on the real machine.

### Option C — run the whole CLI natively on Windows

Only viable if AppLocker is *not* blocking `nxd.exe` (it is, on the known argenx VDI — see
`windows-wsl.md`). If a future environment allows native execution, `nxd mcp config --target
claude --write` from a Windows shell just works, no bridge gymnastics. Default to Option A on the
locked-down VDI, B if A is blocked.

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
- If Desktop doesn't show the server: usually (a) didn't restart, (b) the WSL cross-boundary issue
  (Option A — the `command` must be `wsl.exe`, not a bare Linux path), or (c) the launcher itself
  (`wsl.exe` / `python`) is blocked by AppLocker or quarantined by antivirus on the VDI — try the
  next option down (A → B → C) and, if all are blocked, get IT to whitelist one launcher.
- This whole step depends on Desktop being able to run *some* local command. If the VDI blocks
  every option, MCP-from-Desktop isn't possible there yet — say so plainly rather than leaving the
  learner stuck, and note it as feedback for the platform/field team. The DP itself is still
  deployed and usable; only the Desktop chat-with-your-data convenience is gated.

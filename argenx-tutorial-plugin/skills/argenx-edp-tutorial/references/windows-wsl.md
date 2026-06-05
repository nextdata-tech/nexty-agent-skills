# Windows / WSL / VDI

The argenx learner is almost certainly on **Windows, often a locked-down VDI**. Read this the
moment anything platform-specific appears. The single most important fact:

## ⚠️ Native `nxd.exe` is blocked on the argenx VDI — use WSL

On the customer VDI, the NXD CLI **installs** but `nxd.exe` is **blocked from executing** by
AppLocker / Software Restriction Policies (it lives under `%USERPROFILE%\.local\bin`, which IT
does not permit for execution). This is an IT policy, not a bug — there is no fix on our side.

**The working path is WSL (Ubuntu): the Linux `nxd` binary runs fine.** Treat WSL as *the*
environment for this tutorial on argenx, not a fallback.

How to handle it with the learner:
- If they're already in WSL / a Linux shell (you can tell — `uname` returns `Linux`), proceed
  normally; everything in the tutorial just works.
- If they're in native Windows (PowerShell / CMD) and `nxd` fails to execute (an AppLocker /
  "this app has been blocked" style error, not a "not recognized" PATH error), explain plainly:
  *"Your work laptop's security policy won't let this tool run directly on Windows, but it runs
  perfectly inside WSL — a lightweight Ubuntu environment Windows ships with. Let's switch to
  that."* Then guide them into WSL (`wsl` from a terminal, or open the Ubuntu app).
- Keep it reassuring — this is the company's policy, not anything they did wrong.

Alternatives to mention only if WSL is also unavailable (these need IT and are slow):
whitelist `%USERPROFILE%\.local\bin`, or publisher/hash-rule `nxd.exe` (breaks on updates), or
an approved install location. Default to WSL.

## Antivirus on the VDI (a second, separate gate)

Beyond AppLocker, these VDIs have **antivirus** that can independently block or quarantine things
— an unsigned binary, a freshly-downloaded `.py`, or even outbound HTTPS from an unexpected
process. Symptoms look different from AppLocker: a file vanishing after download, a "blocked by
your administrator" AV popup, or a command that hangs then fails on network. If something that
*should* work silently doesn't, suspect AV, and treat it like AppLocker: it's IT's policy, not the
learner's fault, and the fix is usually a whitelist request. This matters most at the Claude
Desktop / MCP step (`references/mcp-desktop.md`), where whichever launcher you pick (`wsl.exe`,
`python`, `nxd.exe`) has to survive *both* AppLocker and AV.

## Detecting which shell they're in

```bash
uname        # "Linux" => WSL/Linux (good). Fails/"not recognized" => native Windows.
```

## Common native-Windows snags (once in WSL these mostly vanish)

- **"`nxd` is not recognized" / "command not found"** — PATH issue. The installer puts the
  binary in `~/.local/bin`; ensure it's on PATH (`export PATH="$HOME/.local/bin:$PATH"`), or
  reopen the shell. This is *different* from the AppLocker block above.
- **CRLF line endings** — files created on Windows can carry `\r\n`, which breaks shell
  scripts and sometimes Python. Inside WSL, work in the Linux home (`~`), not under
  `/mnt/c/...`, to avoid this.
- **Paths** — use forward slashes inside WSL. The Windows `C:\Users\you` is `/mnt/c/Users/you`
  from WSL, but prefer the native Linux home for project files (faster, no CRLF surprises).

## Cowork note

In Cowork you (the agent) typically have the shell — run steps yourself and show results.
The learner only needs to act for things that genuinely require them: a browser login during
`nxd-setup`, or an Azure consent click. Minimize what you ask them to type.

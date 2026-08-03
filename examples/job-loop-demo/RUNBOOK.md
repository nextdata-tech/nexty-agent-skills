# job-loop live test — Claude Desktop / Cowork

Fixed, reproducible drive of the `nxd-run-job-loop` skill against a small local
CSV export. The point of this run is NOT to test the runtime (the acceptance
suite already proves that on installed wheels) — it is to surface the
**Cowork/Desktop-specific quirks** the automated path can't reach.

## One-time host setup (a normal terminal on the target Mac)

```bash
cd <nxd repo checkout>
components/desktop/supervisor/scripts/nxd-desktop-setup.sh
# Then eval the two export lines it prints:
#   export PATH="$HOME/.nxd/bin:$PATH"
#   export NXD_DESKTOP_PYTHON="$HOME/.nxd/desktop-venv/bin/python"
command -v nxd-desktop-supervisor        # must resolve
command -v nxd-desktop-kernel-host       # must resolve to the SAME dir
```

## Install the LOCAL skill (not the published one)

Install the `nxd-run-job-loop` skill from THIS worktree
(`src/nxd-run-job-loop/`), so we iterate on the preflight fixes. Also install its
dependencies: `nxd-build-semantic-data-product` and `nxd-generate-data-product`.

## Drive the loop (in Claude Desktop / Cowork)

**Intent:** "Build a data product from this orders + customers export so I can
analyze sales by customer country and segment."

**Source:** `examples/job-loop-demo/source` (one dir per table, CSVs inside).

**Questions:**
1. What is the total order amount by customer country?
2. What is the total *paid* order amount by customer country? (exercises a filter)
3. How many orders per customer segment? (exercises the join to customers)

## Expected answers (goldens — for eyeballing correctness)

| Question | Expected |
|---|---|
| Q1 total amount by country (all statuses) | Spain 30.00 · United Kingdom 365.00 · United States 1005.00 |
| Q2 total **paid** amount by country | United Kingdom 365.00 · United States 945.00 (Spain drops — its only order was refunded; US drops the two refunds: 1005 − 60 = 945) |
| Q3 order count by segment | enterprise 7 · smb 3 |

If the model answers these, the loop works end to end in Cowork/Desktop.

## The four quirks to WATCH (why this run exists)

1. **Skill activation** — does the agent actually invoke the `nxd-run-job-loop`
   skill, or fall back to reading `SKILL.md` as a file? Note which.
2. **PATH / env persistence across Bash calls** — after setup, does
   `command -v nxd-desktop-supervisor` still resolve in a LATER Bash call, and is
   `$NXD_DESKTOP_PYTHON` still set? If not, the preflight now tells the agent to
   prefix each command with the exports — confirm it does.
3. **`bearer_token` on stderr** — `serve` prints the bearer to stderr, everything
   else to stdout. Confirm the agent captures BOTH streams and the bearer reaches
   `describe`/`query`. (This was a real doc bug — verified against
   `supervisor_main.rs:242` `eprintln!`.)
4. **Sandbox egress + marker scoping** — did `nxd-desktop-setup.sh` reach
   `nxd.trynxd.com/registry/index/` to pull wheels? Is `~/.nxd/` shared or
   per-project in Cowork? Note the marker location and whether a second project
   re-provisions.

Capture what actually happened at each of the four — that's the deliverable of
this run, and it drives the next round of skill/setup fixes.

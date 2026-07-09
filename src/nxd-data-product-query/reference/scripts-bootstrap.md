# Making `scripts/` reachable from Bash (Step 0 detail)

The `nxd-data-product-query` skill is **script-first**: every step runs
`python3 scripts/<name>.py` from the skill's own directory. That assumes the
shell the Bash tool executes in can see the skill's `scripts/` directory. Not
every agent harness guarantees this.

## The problem

Some harnesses mount only an **allowlisted subset** of an enabled skill's
directory (typically the docs + `SKILL.md`) into the sandbox the Bash/shell tool
operates in. The skill loads fine — its `SKILL.md` was read — but `scripts/` is
absent from the shell's filesystem. A `find /` over the sandbox finds no copy
anywhere.

The failure mode is a **shell** error, not a Python error:

```
python3: can't open file 'scripts/find_mesh.py': [Errno 2] No such file or directory
```

Every subsequent step (`gateway_tools.py`, `connect_port.py`, the venv
`pip install -r scripts/requirements.txt`) fails the same way, so the skill is
non-functional by design in that harness — independent of whether the MCP /
gateway path it wraps is healthy.

## The fix: resolve a `WORKDIR` once per session

1. **Note the skill base directory** — `$SKILL_DIR`, the absolute path this
   `SKILL.md` was read from (the loader provides it at invocation time).

2. **Probe reachability from Bash:**

   ```bash
   if [ -f "$SKILL_DIR/scripts/find_mesh.py" ]; then
     WORKDIR="$SKILL_DIR"      # shell can see the scripts — use them in place
   else
     WORKDIR=""                # not Bash-reachable — bootstrap a copy (step 3)
   fi
   ```

3. **If `WORKDIR` is empty, materialize the scripts into a writable scratch dir.**
   The shell can't reach `$SKILL_DIR/scripts`, but the file-read tools
   (Read / Glob) can read the skill directory, and Write can create files in a
   scratch location the shell *does* see — the session working/output directory,
   e.g. `"$HOME/.nxd-data-product-query-scripts"` or the harness scratch dir:

   - Glob `scripts/**/*` under `$SKILL_DIR` to enumerate every script **plus**
     `scripts/requirements.txt`.
   - Read each and Write it into `<scratch>/scripts/` at the **same relative
     path** — the scripts import each other by filename, so they must stay side
     by side.
   - Set `WORKDIR=<scratch>`.

4. **Run every later `scripts/...` command from `WORKDIR`** — either `cd
   "$WORKDIR"` first, or invoke as `python3 "$WORKDIR/scripts/<name>.py"`. The
   venv in **Scripts** installs from `"$WORKDIR/scripts/requirements.txt"`.

5. **Confirm** with a network-free probe before continuing:

   ```bash
   python3 "$WORKDIR/scripts/find_mesh.py" --help >/dev/null && echo "scripts reachable"
   ```

Cache `WORKDIR` for the whole session — don't re-copy on every call. This makes
the skill self-healing in any harness whose sandbox omits the skill directory,
with no change required on the MCP / gateway side.

# Job loop eval runtime

Build the pinned desktop runtime from the NXD worktree before running this
scenario:

```sh
cargo build -p nxd-desktop-supervisor --bins
uv sync --directory components/desktop/supervisor/py
```

Set both runtime paths. `EVAL_DESKTOP_SUPERVISOR_DIR` must contain both
`nxd-desktop-supervisor` and its sibling `nxd-desktop-kernel-host` binary;
`EVAL_DESKTOP_PYTHON` is the supervisor Python virtualenv interpreter.

```sh
export EVAL_DESKTOP_SUPERVISOR_DIR=/path/to/target/debug
export EVAL_DESKTOP_PYTHON=/path/to/components/desktop/supervisor/py/.venv/bin/python
python evals/run.py --scenario job-loop-serve-query-refine --skill-set candidate_pack
```

The runner preflights the committed reference closure, injects that runtime
only for this opted-in scenario, independently re-serves immutable snapshots,
and tears down persistent supervisor processes.

## Out of scope: offloading generation to a subagent

This scenario is a single-source, direct-CLI loop — precisely the case where the
skill authors generation **inline** (offloading to a subagent is permitted, not
required, and a trivial closure is not worth the dispatch). So it does not — and
should not — exercise the profile/generate subagent split. That behavior and its
safety boundaries (policy read-back stays a main-thread user turn, the subagent
bounces with `gap_found` rather than guessing, a live credential never enters a
subagent, the returned closure path is verified host-side before build) are
pinned by `evals/tests/test_generation_subagent_gate.py`, the same way the
resume-first ordering is pinned by `test_resume_first_gate.py`. Proving the
behavior end-to-end would need a different fixture — an MCP surface, a
multi-source or procedure-bearing closure, and trace access to subagent dispatch
— not this one.

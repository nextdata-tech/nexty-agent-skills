# Pocket loop eval runtime

Build the pinned desktop runtime from the NXD worktree before running this
scenario:

```sh
cargo build -p nxd-desktop-supervisor --bins
uv sync --directory components/desktop/supervisor/py
```

Set both runtime paths. `EVAL_POCKET_SUPERVISOR_DIR` must contain both
`nxd-desktop-supervisor` and its sibling `nxd-desktop-kernel-host` binary;
`EVAL_POCKET_PYTHON` is the supervisor Python virtualenv interpreter.

```sh
export EVAL_POCKET_SUPERVISOR_DIR=/path/to/target/debug
export EVAL_POCKET_PYTHON=/path/to/components/desktop/supervisor/py/.venv/bin/python
python evals/run.py --scenario pocket-loop-serve-query-refine --skill-set candidate_pack
```

The runner preflights the committed reference closure, injects that runtime
only for this opted-in scenario, independently re-serves immutable snapshots,
and tears down persistent supervisor processes.

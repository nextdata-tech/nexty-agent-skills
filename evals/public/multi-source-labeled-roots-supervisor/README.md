# Multi-source labeled roots — live supervisor scenario

This is an opt-in desktop integration scenario. Build a compatible supervisor
runtime first and set:

```sh
export EVAL_DESKTOP_SUPERVISOR_DIR=/path/to/target/debug
export EVAL_DESKTOP_PYTHON=/path/to/components/desktop/supervisor/py/.venv/bin/python
python3 evals/run.py --scenario multi-source-labeled-roots-supervisor \
  --skill-set current_pack --agent-backend codex --judge-backend codex
```

The ordinary `multi-source-labeled-roots` scenario is intentionally runtime
free; this scenario is the explicit live-supervisor boundary.

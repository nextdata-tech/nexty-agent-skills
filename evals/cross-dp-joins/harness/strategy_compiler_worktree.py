"""Strategy A via the WORKTREE compiler + root-principal execution.

This drives strategy A through the *worktree* ``nxd.experimental.semantic``
compiler (the fixed library, run via the nxd_py interpreter) and EXECUTES the
compiled SQL under the root ``LOWERENVS_ROLE`` cross-schema principal — NOT the
deployed DP (which pip-installs the registry library and lags behind a worktree
fix until republished).

Use this to score the matrix against the *current* compiler source without a
build+publish+redeploy cycle. It reuses:
  - ``strategy_compiler_dp``'s harvest (each member DP's semantic_model payload),
  - the worktree compiler's merge+compile (mirrors ``cross_dp_compile.merge_registry``
    + ``compile_cross_dp`` — same two-pass owner-wins), invoked in the nxd_py
    interpreter so the FIXED library resolves,
  - ``freeze_live._connect`` (root key-pair principal) for execution.

Returns the same result dict shape ``run_eval`` expects from strategy A:
``{rows, sql, abstained, errored, error}``.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve().parent
# nxd_py checkout whose compiler we want to exercise (the FIXED worktree).
_NXD_PY_DIR = Path(
    os.environ.get(
        "NXD_PY_DIR",
        "/Volumes/PRO-G40/projects/nxd/.claude/worktrees/t2sql-exp/components/nxd_py",
    )
).resolve()

import strategy_compiler_dp as _dp  # noqa: E402  (reuse its harvest)
import freeze_live as _fl  # noqa: E402  (reuse the root connect)


# The compile runs in the nxd_py interpreter (the fixed lib). This snippet reads a
# {payloads, selection} job on stdin and prints {sql} or {error} on stdout — the
# SAME merge+compile the cross_dp_compile.py client uses, kept inline so this
# driver needs no extra file in the nxd_py tree.
_COMPILE_SNIPPET = r"""
import json, sys
from nxd.experimental.semantic import (
    Agg, Cardinality, CompileError, SemanticRegistry, SnowflakeDialect, compile_selection,
)
job = json.load(sys.stdin)
payloads = job["payloads"]; selection = job["selection"]
_AGG = {a.value: a for a in Agg}; _CARD = {c.value: c for c in Cardinality}
best = {}
for p in payloads:
    for m in p.get("models", []):
        prev = best.get(m["name"])
        if prev is None: best[m["name"]] = m
        elif not prev.get("table") and m.get("table"): best[m["name"]] = m
reg = SemanticRegistry()
for name, m in best.items():
    db = m.get("database") or ""; schema = m.get("schema") or ""
    table = m.get("table") or ((db+"."+schema+"."+name) if (db and schema) else ((schema+"."+name) if schema else ""))
    reg = reg.model(name, grain=m["grain"], description=m.get("description",""),
                    data_product=m.get("data_product",""), table=table)
sd=set(); sm=set(); sj=set()
for p in payloads:
    for d in p.get("dimensions", []):
        if d["name"] in sd: continue
        sd.add(d["name"]); reg = reg.dimension(d["name"], model=d["model"], column=d["column"],
            type=d.get("type","string"), description=d.get("description",""), pii=d.get("pii",False),
            label_column=d.get("label_column"))
    for mt in p.get("metrics", []):
        if mt["name"] in sm: continue
        sm.add(mt["name"]); reg = reg.metric(mt["name"], model=mt["model"], agg=_AGG[mt["agg"]],
            column=mt.get("column","*"), description=mt.get("description",""), boolean=mt.get("boolean",False))
    for j in p.get("joins", []):
        key=(j["left"], j["right"], tuple(tuple(o) for o in j["on"]))
        if key in sj: continue
        sj.add(key); reg = reg.join(left=j["left"], right=j["right"],
            on=tuple((a,b) for a,b in j["on"]),
            cardinality=_CARD.get(j.get("cardinality","many_to_one"), Cardinality.MANY_TO_ONE))
reg = reg.build()
try:
    sql = compile_selection(selection, registry=reg, dialect=SnowflakeDialect(view_name=""), fqn="", use_view=False)
    print(json.dumps({"sql": sql}))
except CompileError as e:
    print(json.dumps({"error": "CompileError: %s" % e}))
except Exception as e:
    print(json.dumps({"error": "Compile failed: %s" % e}))
"""


def _compile_worktree(payloads: list[dict], selection: dict) -> tuple[str | None, str | None]:
    """Compile via the worktree lib (nxd_py interpreter). Returns (sql, error)."""
    proc = subprocess.run(
        ["uv", "run", "python", "-c", _COMPILE_SNIPPET],
        cwd=str(_NXD_PY_DIR),
        input=json.dumps({"payloads": payloads, "selection": selection}),
        capture_output=True,
        text=True,
        timeout=180,
    )
    if proc.returncode != 0:
        return None, f"compile subprocess failed: {proc.stderr.strip()[:300]}"
    try:
        out = json.loads(proc.stdout.strip().splitlines()[-1])
    except Exception as e:  # noqa: BLE001
        return None, f"compile output parse failed: {e}: {proc.stdout[:200]}"
    return out.get("sql"), out.get("error")


def run_compiler_worktree_strategy(
    question: dict, *, token_file: str, api_url: str | None = None
) -> dict[str, Any]:
    """Harvest -> worktree-compile (fixed lib) -> root-exec -> result dict."""
    sel = question.get("compiler_selection")
    if not sel:
        return {"rows": None, "sql": None, "abstained": False, "errored": True,
                "error": "no compiler_selection on question"}
    import tempfile

    try:
        with tempfile.TemporaryDirectory() as td:
            raw = _dp.harvest_payloads(sel.get("dps", []), token_file, Path(td))
        # harvest_payloads returns the payload JSON strings; parse to dicts.
        payloads = [json.loads(p) if isinstance(p, str) else p for p in raw]
    except Exception as e:  # noqa: BLE001
        return {"rows": None, "sql": None, "abstained": False, "errored": True,
                "error": f"harvest failed: {e}"}

    selection = {"measures": sel.get("measures", []), "dimensions": sel.get("dimensions", []),
                 "filters": sel.get("filters", [])}
    sql, err = _compile_worktree(payloads, selection)
    if err or not sql:
        return {"rows": None, "sql": sql, "abstained": False, "errored": True, "error": err or "no SQL"}

    conn = _fl._connect()
    try:
        cur = conn.cursor()
        cur.execute(sql)
        cols = [d[0].lower() for d in cur.description]
        rows = [dict(zip(cols, r)) for r in cur.fetchall()]
    except Exception as e:  # noqa: BLE001
        return {"rows": None, "sql": sql, "abstained": False, "errored": True, "error": f"exec failed: {e}"}
    finally:
        conn.close()
    return {"rows": rows, "sql": sql, "abstained": False, "errored": False, "error": ""}

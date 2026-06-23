#!/usr/bin/env python3
"""Strategy A (deterministic cross-DP compiler) driver for ONE question.

Given a concept selection ``{measures, dimensions}`` and the set of DPs that own
the referenced models, this drives the full compiler path end to end:

    1. HARVEST  each needed DP's ``semantic_model`` MCP tool, serially, each to a
                PER-DP ``--out`` file (``mcp_call.py`` reuses one fixed /tmp path,
                so concurrent harvest races — serial + per-DP out is the only safe
                shape). Run with the SKILL python (needs ``requests``).
    2. COMPILE  feed the saved per-DP payloads to ``cross_dp_compile.py`` via
                ``--registry-json PATH=SCHEMA`` so it merges them into ONE
                SemanticRegistry and emits ONE fan-out-safe cross-schema SQL. Run
                with the WORKTREE nxd_py interpreter (needs the 0.41.99-dev5
                ``nxd.experimental.semantic`` library; the skill's global python is
                too old and TypeErrors on the registry API).
    3. VERIFY   re-assert the two-pass merge fix: EVERY FROM/JOIN relation in the
                compiled SQL must be fully schema-qualified as
                ``LOWERENVS_DB.<SCHEMA>.<table>`` for a known mesh schema. A bare
                relation or a wrong-schema relation means a tableless stub won the
                merge — fail loud rather than execute a mis-qualified join.
    4. EXECUTE  run the compiled SQL once via ``harness.live_exec`` (a leased
                Snowflake cred whose role can read every referenced schema).

Returns ``{sql, rows, deterministic_hash, fanout_safe}`` for one question.

The two python environments are bridged on disk: harvest writes JSON payloads
the compiler reads back. Neither subprocess shares an interpreter with this
module — this module only orchestrates and parses their JSON.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

# ---------------------------------------------------------------------------
# Locations / interpreters
# ---------------------------------------------------------------------------

_HERE = Path(__file__).resolve().parent

# The query skill (harvest + compiler client both live here).
_SKILL_SCRIPTS = Path(
    os.environ.get(
        "NXD_QUERY_SKILL_SCRIPTS",
        "/Volumes/PRO-G40/projects/nexty-agent-skills/src/nxd-data-product-query/scripts",
    )
).resolve()
_MCP_CALL = _SKILL_SCRIPTS / "mcp_call.py"
_CROSS_DP_COMPILE = _SKILL_SCRIPTS / "cross_dp_compile.py"

# The worktree nxd_py package dir: `uv run python` there resolves the dev nxd lib
# the compiler imports. The skill's plain python3 runs harvest.
_NXD_PY_DIR = Path(
    os.environ.get(
        "NXD_PY_DIR",
        "/Volumes/PRO-G40/projects/nxd/components/nxd_py",
    )
).resolve()
_SKILL_PYTHON = os.environ.get("NXD_SKILL_PYTHON", "python3")

# CA bundle for the local self-signed mesh (mcp_call upgrades http->https).
_CA_BUNDLE = os.environ.get(
    "NXD_CA_BUNDLE",
    "/Volumes/PRO-G40/projects/nxd/shared/charts/nxd/localCerts/nxdCA.crt",
)

# The single Snowflake database every pharma DP lives under.
DATABASE = os.environ.get("NXD_MESH_DATABASE", "LOWERENVS_DB")

# DP fullName-stem -> its Snowflake schema + live MCP endpoint. These are the
# 7 pharma mesh DPs (verified live). Endpoint pattern:
#   http://nxd.nxd.local/dp/<dp>-demo/rpcs/mcp-api/mcp/
_MESH_BASE = os.environ.get("NXD_MESH_BASE", "http://nxd.nxd.local")
PHARMA_DPS: dict[str, str] = {
    "pharma-labs-demo": "PHARMA_LABS_DEMO",
    "pharma-rx-demo": "PHARMA_RX_DEMO",
    "pharma-subjects-demo": "PHARMA_SUBJECTS_DEMO",
    "pharma-sites-demo": "PHARMA_SITES_DEMO",
    "pharma-visits-demo": "PHARMA_VISITS_DEMO",
    "pharma-safety-demo": "PHARMA_SAFETY_DEMO",
    "pharma-product-demo": "PHARMA_PRODUCT_DEMO",
}


def _endpoint(dp: str) -> str:
    return f"{_MESH_BASE}/dp/{dp}/rpcs/mcp-api/mcp/"


# ---------------------------------------------------------------------------
# 1. HARVEST — serial, per-DP --out (mcp_call.py reuses one /tmp path)
# ---------------------------------------------------------------------------


def harvest_one(dp: str, token_file: str, out_path: Path, *, timeout: int = 60) -> dict:
    """Call one DP's ``semantic_model`` tool with the SKILL python; return payload.

    Writes to a PER-DP ``out_path`` to avoid the shared-/tmp race. Unwraps the
    ``{"payload": "<json string>"}`` envelope the tool returns.
    """
    cmd = [
        _SKILL_PYTHON,
        str(_MCP_CALL),
        "--endpoint", _endpoint(dp),
        "--tool", "semantic_model",
        "--args", "{}",
        "--token-file", token_file,
        "--out", str(out_path),
        "--ca-bundle", _CA_BUNDLE,
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    if proc.returncode != 0:
        raise RuntimeError(
            f"harvest {dp} failed (rc={proc.returncode}): {proc.stderr.strip() or proc.stdout.strip()}"
        )
    raw = json.loads(out_path.read_text(encoding="utf-8"))
    payload = raw.get("payload", raw)
    if isinstance(payload, str):
        payload = json.loads(payload)
    return payload


def harvest(dps: list[str], token_file: str, work_dir: Path) -> dict[str, Path]:
    """Serially harvest each DP -> per-DP payload file. Returns {dp: path}."""
    out: dict[str, Path] = {}
    for dp in dps:
        path = work_dir / f"registry-{dp}.json"
        payload = harvest_one(dp, token_file, path)
        # re-write the UNWRAPPED payload so the compiler reads a bare registry doc
        path.write_text(json.dumps(payload), encoding="utf-8")
        out[dp] = path
    return out


# ---------------------------------------------------------------------------
# 2. COMPILE — cross_dp_compile.py under the nxd_py interpreter
# ---------------------------------------------------------------------------


def compile_sql(
    measures: list[str],
    dimensions: list[str],
    payload_files: dict[str, Path],
    schema_of_dp: dict[str, str],
    out_sql: Path,
    *,
    timeout: int = 120,
) -> str:
    """Run the compiler client; return the compiled SQL string.

    Invokes ``cross_dp_compile.py`` via ``uv run python`` from the nxd_py dir so
    the dev ``nxd.experimental.semantic`` import resolves. Each per-DP payload is
    passed as ``--registry-json PATH=SCHEMA`` (offline merge path — no live calls
    from inside the nxd_py interpreter, which lacks the session token plumbing).
    """
    cmd = [
        "uv", "run", "python",
        str(_CROSS_DP_COMPILE),
        "--measures", ",".join(measures),
        "--dimensions", ",".join(dimensions),
        "--out", str(out_sql),
    ]
    for dp, path in payload_files.items():
        schema = schema_of_dp[dp]
        cmd += ["--registry-json", f"{path}={schema}"]

    proc = subprocess.run(
        cmd, capture_output=True, text=True, timeout=timeout, cwd=str(_NXD_PY_DIR)
    )
    if proc.returncode != 0:
        raise RuntimeError(
            f"compile failed (rc={proc.returncode}): {proc.stderr.strip() or proc.stdout.strip()}"
        )
    result = json.loads(proc.stdout)
    if "error" in result:
        raise RuntimeError(f"compile error: {result['error']}")
    return result["sql"]


# ---------------------------------------------------------------------------
# 3. VERIFY — every relation is LOWERENVS_DB.<known-schema>.<table>
# ---------------------------------------------------------------------------

import re

# captures the relation token after FROM / JOIN
_REL_RE = re.compile(r"\b(?:FROM|JOIN)\s+([A-Za-z_][\w.]*)", re.IGNORECASE)
# names declared as CTEs: `WITH a AS (`, `), d AS (`
_CTE_RE = re.compile(r"(?:\bWITH\b|,)\s*([A-Za-z_]\w*)\s+AS\s*\(", re.IGNORECASE)


def _cte_names(sql: str) -> set[str]:
    return {m.group(1).upper() for m in _CTE_RE.finditer(sql)}


def assert_schema_qualified(sql: str, database: str, schemas: set[str]) -> None:
    """Fail loud unless every physical FROM/JOIN relation is DB.<known-schema>.<tbl>.

    Re-verifies the two-pass merge fix: a tableless stub winning the merge yields
    a bare or wrong-schema relation. A single-token relation is allowed ONLY when
    it names a CTE declared in this statement's ``WITH`` clause — a bare physical
    table (``FROM assays``) is the exact regression and fails loud.
    """
    bad: list[str] = []
    db_up = database.upper()
    schemas_up = {s.upper() for s in schemas}
    ctes = _cte_names(sql)
    for m in _REL_RE.finditer(sql):
        rel = m.group(1)
        parts = rel.split(".")
        if len(parts) == 1:
            if rel.upper() in ctes:
                continue  # CTE reference, not a physical table
            bad.append(f"{rel} (bare relation — not a declared CTE, expected DB.SCHEMA.TABLE)")
            continue
        if len(parts) != 3:
            bad.append(f"{rel} (not DB.SCHEMA.TABLE — got {len(parts)} parts)")
            continue
        db, schema, _tbl = parts
        if db.upper() != db_up:
            bad.append(f"{rel} (wrong database, expected {database})")
        elif schema.upper() not in schemas_up:
            bad.append(f"{rel} (unknown schema {schema})")
    if bad:
        raise AssertionError(
            "compiled SQL has non-/mis-qualified relations (merge fix regressed): "
            + "; ".join(bad)
        )


def deterministic_hash(sql: str) -> str:
    """Stable hash of the normalized compiled SQL (whitespace-collapsed)."""
    norm = " ".join(sql.split())
    return hashlib.sha256(norm.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# 4. EXECUTE + fan-out check (deferred to sibling harness modules)
# ---------------------------------------------------------------------------


def _resolve_api_url() -> tuple[str, str | None]:
    """Resolve the live mesh (api_url, token_file) via the skill's find_mesh.py.

    Mirrors ``live_exec._smoke``: the mesh endpoint is not a static constant,
    it's discovered at runtime. Returns (api_url, token_file_or_None).
    """
    find_mesh = _SKILL_SCRIPTS / "find_mesh.py"
    proc = subprocess.run(
        [sys.executable, str(find_mesh)],
        capture_output=True,
        text=True,
        check=True,
    )
    mesh = json.loads(proc.stdout)
    return mesh["api_url"], mesh.get("token_file")


def _live_exec(sql: str, lease_dp: str, port: str, token_file: str | None):
    """Execute via ``live_exec.run`` (lease-per-call). Returns list[dict].

    DEFECT 3 fix: the prior code called ``live_exec.execute(sql, creds_file=...)``
    but live_exec exposes no such function/param — the ``creds_file`` concept does
    not exist. The real entrypoint is ``live_exec.run(sql, *, dp, port, api_url,
    token_file, ...)``, which leases a credential against the DP's output port then
    executes once. We resolve ``api_url`` at runtime via find_mesh.py.
    """
    from harness import live_exec  # type: ignore[import-not-found]

    api_url, mesh_token = _resolve_api_url()
    result = live_exec.run(
        sql,
        dp=lease_dp,
        port=port,
        api_url=api_url,
        token_file=token_file or mesh_token,
    )
    return _rows_to_dicts(result)


def _rows_to_dicts(result) -> list[dict]:
    if result is None:
        return []
    if isinstance(result, list):
        return result  # already list[dict]
    cols = result.get("columns") or []
    rows = result.get("rows") or []
    out = []
    for r in rows:
        if isinstance(r, dict):
            out.append({k.lower(): v for k, v in r.items()})
        else:
            out.append({str(c).lower(): v for c, v in zip(cols, r)})
    return out


def _fanout_safe(sql: str) -> str:
    """FANOUT_SAFE / FANOUT_RISK / N/A via the PoC structure_check (offline)."""
    try:
        from harness import structure_check  # type: ignore[import-not-found]
    except ImportError:
        # PoC harness not importable here — surface as N/A rather than crash.
        return "N/A"
    return structure_check.verdict(sql)


# ---------------------------------------------------------------------------
# Orchestration entrypoint
# ---------------------------------------------------------------------------


def run_compiler_strategy(
    measures: list[str],
    dimensions: list[str],
    dps: list[str],
    token_file: str,
    *,
    schema_of_dp: dict[str, str] | None = None,
    database: str = DATABASE,
    lease_dp: str | None = None,
    lease_port: str = "default",
    execute: bool = True,
    work_dir: Path | None = None,
) -> dict:
    """Drive strategy A for ONE question's {measures, dimensions}.

    Returns ``{sql, rows, deterministic_hash, fanout_safe}``. ``rows`` is None
    when ``execute=False``.
    """
    schema_of_dp = schema_of_dp or PHARMA_DPS
    unknown = [d for d in dps if d not in schema_of_dp]
    if unknown:
        raise ValueError(f"unknown DP(s) with no schema mapping: {unknown}")

    owns_tmp = work_dir is None
    work_dir = work_dir or Path(tempfile.mkdtemp(prefix="cross-dp-compiler-"))
    work_dir.mkdir(parents=True, exist_ok=True)

    payload_files = harvest(dps, token_file, work_dir)
    out_sql = work_dir / "compiled.sql"
    sql = compile_sql(measures, dimensions, payload_files, schema_of_dp, out_sql)

    schemas = {schema_of_dp[d] for d in dps}
    assert_schema_qualified(sql, database, schemas)

    # Lease against ONE of the joined DPs' output port (any of them grants the
    # leased Snowflake role that can read the schema-qualified cross-DP SQL).
    lease_target = lease_dp or dps[0]
    rows = _live_exec(sql, lease_target, lease_port, token_file) if execute else None

    result = {
        "sql": sql,
        "rows": rows,
        "deterministic_hash": deterministic_hash(sql),
        "fanout_safe": _fanout_safe(sql),
    }
    if owns_tmp:
        result["_work_dir"] = str(work_dir)
    return result


# ---------------------------------------------------------------------------
# Smoke CLI: titer_sum + units_dispensed by subject_country (the chasm case)
# ---------------------------------------------------------------------------


def _default_token_file() -> str:
    """Run find_mesh.py with the skill python; read .token_file from its JSON."""
    proc = subprocess.run(
        [_SKILL_PYTHON, str(_SKILL_SCRIPTS / "find_mesh.py")],
        capture_output=True, text=True, timeout=60,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"find_mesh failed: {proc.stderr.strip()}")
    tok = json.loads(proc.stdout).get("token_file")
    if not tok:
        raise RuntimeError("find_mesh returned no token_file (run `nxd whoami` first)")
    return tok


def main() -> int:
    p = argparse.ArgumentParser(prog="strategy_compiler")
    p.add_argument("--measures", default="titer_sum,units_dispensed")
    p.add_argument("--dimensions", default="subject_country")
    p.add_argument(
        "--dps",
        default="pharma-labs-demo,pharma-rx-demo,pharma-subjects-demo,pharma-sites-demo",
        help="comma-separated DP stems whose models the selection references",
    )
    p.add_argument("--token-file", default="", help="session token (default: find_mesh.py)")
    p.add_argument("--lease-dp", default="", help="DP to lease the output-port credential against (default: first --dps stem)")
    p.add_argument("--lease-port", default="default", help="output port name to lease (default: default)")
    p.add_argument("--no-execute", action="store_true", help="compile + verify only, skip live run")
    args = p.parse_args()

    token_file = args.token_file or _default_token_file()
    result = run_compiler_strategy(
        measures=[m for m in args.measures.split(",") if m],
        dimensions=[d for d in args.dimensions.split(",") if d],
        dps=[d for d in args.dps.split(",") if d],
        token_file=token_file,
        lease_dp=args.lease_dp or None,
        lease_port=args.lease_port,
        execute=not args.no_execute,
    )
    print(json.dumps(result, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

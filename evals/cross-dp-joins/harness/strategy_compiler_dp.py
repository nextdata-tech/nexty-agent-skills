#!/usr/bin/env python3
"""Strategy A — the DEPLOYED server-side cross-DP compiler DP (WireA).

This REPLACES the client stand-in (``strategy_compiler.py``, whose offline
``cross_dp_compile.py`` path is IP-blocked from the laptop). Strategy A is now
the live mesh DP ``cross-dp-query-demo-demo``, which serves the MCP tool
``run_cross_dp_query``. That DP:

  - accepts the member DPs' ``semantic_model`` payloads (each a JSON string),
  - merges them (two-pass, owner-wins) into ONE SemanticRegistry,
  - compiles ONE fan-out-safe cross-schema SQL,
  - executes it IN-POD under ``LOWERENVS_ROLE`` (cross-schema USAGE — the in-pod
    role is reachable where the per-DP TEMPORAL lease is IP-blocked).

So WireA is a pure orchestration of two MCP tools, no nxd_py interpreter, no
offline compile, no Snowflake lease:

  1. SELECT  the member DPs the question spans (from the gold record's
             ``compiler_selection.dps`` if present, else harvest all 5 and let
             the compiler pick which models the measures/dimensions touch).
  2. HARVEST each needed DP's ``semantic_model`` tool, serially, each to a PER-DP
             ``--out`` file (mcp_call.py reuses a fixed /tmp path otherwise), and
             collect the ``{"payload": "<json string>"}`` payload STRINGS verbatim
             (the cross-DP tool wants the raw registry-payload strings).
  3. COMPILE+EXECUTE in one shot: call ``run_cross_dp_query`` on the compiler DP
             with ``{registry_payloads, measures, dimensions, filters}``.
  4. PARSE   the ``{compiled_sql, row_count, columns, rows, error}`` envelope:
             ``rows`` is a list of JSON-encoded arrays — zip each against
             ``columns`` and lowercase the keys to get list[dict].

Returns the SAME result shape ``strategy_compiler.run_compiler_strategy`` did
({sql, rows, deterministic_hash, fanout_safe}) PLUS the trial-record shape
``run_eval`` builds from it via ``run_compiler_dp_strategy`` — see that function.

ABSTAIN vs ERROR (mirrors gold_cross_dp.py): the compiler does NOT abstain. A
CompileError-style failure (e.g. x17 "at least one metric is required") comes
back in the tool's ``error`` field or as an ``isError`` envelope; WireA maps that
to ``errored=True`` (NOT abstained). The strict agent (strategy B) is the one
that abstains.

DP-name shape: the gold records / mesh-context name member DPs by their fullName
stem (``pharma-labs-demo``); the LIVE per-DP MCP route appends the env segment
(``pharma-labs-demo-demo``). ``_route_stem`` bridges the two so a selection can
carry either form.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

_HERE = Path(__file__).resolve().parent
# repo root = …/evals/cross-dp-joins/harness -> up 3.
_REPO_ROOT = _HERE.parents[2]

_SKILL_SCRIPTS = Path(
    os.environ.get(
        "NXD_QUERY_SKILL_SCRIPTS",
        str(_REPO_ROOT / "src" / "nxd-data-product-query" / "scripts"),
    )
).resolve()
_MCP_CALL = _SKILL_SCRIPTS / "mcp_call.py"
_SKILL_PYTHON = os.environ.get("NXD_SKILL_PYTHON", "python3")

# CA bundle for the self-signed mesh; mcp_call upgrades http->https.
_CA_BUNDLE = os.environ.get("NXD_CA_BUNDLE")

_MESH_BASE = os.environ.get("NXD_MESH_BASE", "https://nxd.nxd.local")

# Env segment the LIVE per-DP MCP route appends to a fullName stem. The mesh
# context names DPs ``pharma-labs-demo`` but routes them at
# ``/dp/pharma-labs-demo-demo/...`` — i.e. the env segment is appended even though
# the fullName stem already ENDS in ``-demo`` (the stem's own ``-demo`` is part of
# the name, not the env). So the suffix is appended UNCONDITIONALLY. Override via
# NXD_MESH_ENV_SUFFIX (set to "" if a future mesh routes by bare fullName).
_ENV_SUFFIX = os.environ.get("NXD_MESH_ENV_SUFFIX", "-demo")

# The deployed compiler DP route stem (ALREADY env-suffixed — pass it verbatim,
# never re-suffix it). Serves the run_cross_dp_query tool.
COMPILER_DP = os.environ.get("NXD_COMPILER_DP", "cross-dp-query-demo-demo")
COMPILER_TOOL = "run_cross_dp_query"

# All member DPs (fullName stems). Used when a question carries no explicit
# ``dps`` selection — harvest them all and let the compiler pick which models the
# measures/dimensions reference.
ALL_MEMBER_DPS: list[str] = [
    "pharma-subjects-demo",
    "pharma-sites-demo",
    "pharma-labs-demo",
    "pharma-rx-demo",
    "pharma-product-demo",
]


def _route_stem(dp: str) -> str:
    """fullName stem -> the live MCP-route stem (env segment appended).

    The env segment is appended UNCONDITIONALLY because a fullName stem can
    legitimately already end in the suffix token (e.g. ``pharma-labs-demo`` ->
    ``pharma-labs-demo-demo``). The only stem that is ALREADY a route stem is
    ``COMPILER_DP`` (handled by ``_endpoint``, which never re-suffixes it).
    """
    if _ENV_SUFFIX:
        return f"{dp}{_ENV_SUFFIX}"
    return dp


def _endpoint(dp: str, *, already_routed: bool = False) -> str:
    stem = dp if already_routed else _route_stem(dp)
    return f"{_MESH_BASE.rstrip('/')}/dp/{stem}/rpcs/mcp-api/mcp/"


# --------------------------------------------------------------------------- #
# 1+2. HARVEST member semantic_model payloads (serial, per-DP --out)
# --------------------------------------------------------------------------- #


def harvest_payload(dp: str, token_file: str, out_path: Path, *, timeout: int = 60) -> str:
    """Call one member DP's ``semantic_model`` tool; return the raw payload STRING.

    The cross-DP tool wants ``registry_payloads`` as the list of JSON-string
    payloads exactly as ``semantic_model`` returns them (``{"payload": "<str>"}``),
    so we keep the string verbatim — do NOT re-serialize a parsed object.
    """
    cmd = [
        _SKILL_PYTHON,
        str(_MCP_CALL),
        "--endpoint", _endpoint(dp),
        "--tool", "semantic_model",
        "--args", "{}",
        "--token-file", token_file,
        "--out", str(out_path),
    ]
    if _CA_BUNDLE:
        cmd += ["--ca-bundle", _CA_BUNDLE]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    if proc.returncode != 0:
        raise RuntimeError(
            f"harvest {dp} failed (rc={proc.returncode}): "
            f"{proc.stderr.strip() or proc.stdout.strip()}"
        )
    raw = json.loads(out_path.read_text(encoding="utf-8"))
    payload = raw.get("payload", raw) if isinstance(raw, dict) else raw
    if not isinstance(payload, str):
        # The tool returned an already-parsed object — re-encode so the compiler
        # DP receives a JSON string in every case.
        payload = json.dumps(payload)
    return payload


def harvest_payloads(dps: list[str], token_file: str, work_dir: Path) -> list[str]:
    """Serially harvest each DP -> list of payload JSON strings (selection order)."""
    out: list[str] = []
    for dp in dps:
        path = work_dir / f"registry-{_route_stem(dp)}.json"
        out.append(harvest_payload(dp, token_file, path))
    return out


# --------------------------------------------------------------------------- #
# 3. COMPILE + EXECUTE — one run_cross_dp_query call on the compiler DP
# --------------------------------------------------------------------------- #


def call_compiler_dp(
    registry_payloads: list[str],
    measures: list[str],
    dimensions: list[str],
    filters: list,
    token_file: str,
    out_path: Path,
    *,
    timeout: int = 180,
) -> dict:
    """Call ``run_cross_dp_query`` on the compiler DP; return the unwrapped result.

    Returns the tool's envelope dict ``{compiled_sql, row_count, columns, rows,
    error, ...}``. On an MCP-level failure (mcp_call exits non-zero) raises — the
    caller maps that to ``errored``.
    """
    args = {
        "registry_payloads": registry_payloads,
        "measures": measures,
        "dimensions": dimensions,
        "filters": filters or [],
    }
    cmd = [
        _SKILL_PYTHON,
        str(_MCP_CALL),
        "--endpoint", _endpoint(COMPILER_DP, already_routed=True),
        "--tool", COMPILER_TOOL,
        "--args", json.dumps(args),
        "--token-file", token_file,
        "--out", str(out_path),
    ]
    if _CA_BUNDLE:
        cmd += ["--ca-bundle", _CA_BUNDLE]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    summary_is_error = False
    if proc.stdout.strip():
        try:
            summary_is_error = bool(json.loads(proc.stdout).get("is_error"))
        except json.JSONDecodeError:
            pass
    if proc.returncode != 0:
        raise RuntimeError(
            f"run_cross_dp_query MCP call failed (rc={proc.returncode}): "
            f"{proc.stderr.strip() or proc.stdout.strip()}"
        )
    result = json.loads(out_path.read_text(encoding="utf-8"))
    if isinstance(result, dict):
        # Carry the MCP envelope's isError flag through so a CompileError that the
        # tool surfaces ONLY via isError (no ``error`` field) is still seen.
        result.setdefault("_mcp_is_error", summary_is_error)
    return result


# --------------------------------------------------------------------------- #
# 4. PARSE — {compiled_sql,row_count,columns,rows,error} -> list[dict]
# --------------------------------------------------------------------------- #


def _rows_to_dicts(columns: list[str], rows: list) -> list[dict]:
    """Zip each row against ``columns``, lowercasing keys.

    ``run_cross_dp_query`` returns ``rows`` as a list of JSON-encoded arrays
    (``'["US", 495.0, 120.0]'``); decode each before zipping. A row that is
    already a list or dict is handled too (defensive).
    """
    cols = [str(c).lower() for c in (columns or [])]
    out: list[dict] = []
    for r in rows or []:
        if isinstance(r, str):
            try:
                r = json.loads(r)
            except json.JSONDecodeError:
                r = [r]
        if isinstance(r, dict):
            out.append({str(k).lower(): v for k, v in r.items()})
        else:
            out.append({c: v for c, v in zip(cols, r)})
    return out


def _deterministic_hash(sql: str) -> str:
    return hashlib.sha256(" ".join((sql or "").split()).encode("utf-8")).hexdigest()


# --------------------------------------------------------------------------- #
# Orchestration entrypoint — the run_eval seam
# --------------------------------------------------------------------------- #


def run_compiler_dp_strategy(question_record: dict, *, api_url: str | None, token_file: str) -> dict:
    """Drive strategy A (deployed compiler DP) for ONE question.

    Returns a result dict matching what run_eval's trial-record builder expects
    (same shape as ``strategy_compiler.run_compiler_strategy`` PLUS the explicit
    ``{abstained, errored, error}`` flags so the seam can build the trial record
    directly)::

        {rows, sql, abstained, errored, error,
         row_count, columns, deterministic_hash}

    ``question_record`` must carry a ``compiler_selection`` dict
    ``{measures, dimensions, filters?, dps?}`` (authored on the re-authored gold
    record alongside the strict agent's naming). When ``dps`` is absent, ALL
    member DPs are harvested and the compiler picks the models it needs.

    ``api_url`` is accepted for signature parity with the strict-agent driver;
    the per-DP MCP routes are derived from ``NXD_MESH_BASE`` (the api_url's host),
    so it is currently informational only.
    """
    sel = question_record.get("compiler_selection") or question_record.get("selection")
    if not sel:
        return {
            "rows": None,
            "sql": None,
            "abstained": False,
            "errored": True,
            "error": "no compiler_selection on question (cannot drive strategy A)",
        }

    measures = list(sel.get("measures") or [])
    dimensions = list(sel.get("dimensions") or [])
    filters = list(sel.get("filters") or [])
    dps = list(sel.get("dps") or ALL_MEMBER_DPS)

    work_dir = Path(tempfile.mkdtemp(prefix="wirea-compiler-dp-"))
    try:
        payloads = harvest_payloads(dps, token_file, work_dir)
        result_path = work_dir / "cross-dp-result.json"
        envelope = call_compiler_dp(
            payloads, measures, dimensions, filters, token_file, result_path
        )
    except Exception as exc:  # noqa: BLE001 — MCP/transport failure scores ERROR
        return {
            "rows": None,
            "sql": None,
            "abstained": False,
            "errored": True,
            "error": str(exc),
        }

    tool_error = (envelope.get("error") or "").strip() if isinstance(envelope, dict) else ""
    mcp_is_error = bool(envelope.get("_mcp_is_error")) if isinstance(envelope, dict) else False
    # A tool-level CompileError-style message OR an isError envelope is an ERROR,
    # NOT an abstain — the compiler over-reaches rather than declines
    # (gold_cross_dp.py note). The strict agent owns abstention.
    errored = bool(tool_error or mcp_is_error)

    sql = envelope.get("compiled_sql") if isinstance(envelope, dict) else None
    columns = envelope.get("columns") if isinstance(envelope, dict) else None
    raw_rows = envelope.get("rows") if isinstance(envelope, dict) else None
    rows = None if errored else _rows_to_dicts(columns or [], raw_rows or [])

    return {
        "rows": rows,
        "sql": None if errored else sql,
        "abstained": False,
        "errored": errored,
        "error": tool_error or (None if not errored else "run_cross_dp_query isError"),
        "row_count": envelope.get("row_count") if isinstance(envelope, dict) else None,
        "columns": [str(c).lower() for c in (columns or [])],
        "deterministic_hash": _deterministic_hash(sql or ""),
        "_work_dir": str(work_dir),
    }


# --------------------------------------------------------------------------- #
# Smoke CLI: x07 alone (the chasm discriminator)
# --------------------------------------------------------------------------- #


def _default_token_file() -> str:
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
    import argparse

    p = argparse.ArgumentParser(prog="strategy_compiler_dp")
    p.add_argument("--measures", default="titer_sum,units_dispensed")
    p.add_argument("--dimensions", default="subject_country")
    p.add_argument(
        "--dps",
        default="pharma-labs-demo,pharma-rx-demo,pharma-subjects-demo,pharma-sites-demo",
    )
    p.add_argument("--token-file", default="")
    args = p.parse_args()

    token_file = args.token_file or _default_token_file()
    qrec = {
        "id": "x07",
        "compiler_selection": {
            "measures": [m for m in args.measures.split(",") if m],
            "dimensions": [d for d in args.dimensions.split(",") if d],
            "filters": [],
            "dps": [d for d in args.dps.split(",") if d],
        },
    }
    result = run_compiler_dp_strategy(qrec, api_url=None, token_file=token_file)
    print(json.dumps(result, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Freeze the LIVE cross-DP gold into oracle_live.json.

INDEPENDENT ground truth — NOT the server-side compiler. Connects with the root
LOWERENVS_ROLE key-pair principal from .nxd/lowerenvs_ip.yaml (cross-schema
USAGE, not IP-blocked), runs each GOLD_CROSS_DP_LIVE canonical_sql, and captures
rows + a mode-aware stable hash per id. Records flagged ``skipped`` are recorded
with their reason and NOT executed.

Reuses examples/t2sql-poc/gold/freeze_gold.{stable_hash,_rows_from_cursor} so the
hash and column-lowercasing match what the harness scores against.
"""

from __future__ import annotations

import json
import os
import sys

import yaml
import snowflake.connector
from cryptography.hazmat.primitives.serialization import (
    Encoding,
    NoEncryption,
    PrivateFormat,
    load_pem_private_key,
)

_POC_ROOT = "/Volumes/PRO-G40/projects/nxd/.claude/worktrees/t2sql-exp/examples/t2sql-poc"
if _POC_ROOT not in sys.path:
    sys.path.insert(0, _POC_ROOT)

from gold.freeze_gold import stable_hash, _rows_from_cursor  # noqa: E402

_HARNESS_DIR = os.path.dirname(os.path.abspath(__file__))
if _HARNESS_DIR not in sys.path:
    sys.path.insert(0, _HARNESS_DIR)

from gold_cross_dp_live import GOLD_CROSS_DP_LIVE  # noqa: E402

IP_PATH = "/Volumes/PRO-G40/projects/nxd/.nxd/lowerenvs_ip.yaml"
OUT_PATH = os.path.join(_HARNESS_DIR, "oracle_live.json")


def _connect():
    ip = yaml.safe_load(open(IP_PATH))
    svc = next(
        s for s in ip["spec"]["services"] if s["name"] == "nxd-snowflake-keypair"
    )
    a = {x["key"]: x["value"] for x in svc["attributes"]}
    der = load_pem_private_key(
        a["private_key_pem"].encode(), password=None
    ).private_bytes(Encoding.DER, PrivateFormat.PKCS8, NoEncryption())
    return snowflake.connector.connect(
        account=a["account"],
        user=a["user"],
        role=a["role"],
        warehouse=a["warehouse"],
        database=a["database"],
        private_key=der,
    )


def freeze_live(con) -> dict:
    oracle: dict[str, dict] = {}
    for rec in GOLD_CROSS_DP_LIVE:
        qid = rec["id"]
        if rec.get("skipped"):
            oracle[qid] = {"skipped": rec["skipped"]}
            continue
        cur = con.cursor()
        try:
            cur.execute(rec["canonical_sql"])
            rows = _rows_from_cursor(cur)
        finally:
            cur.close()
        oracle[qid] = {
            "rows": rows,
            "row_hash": stable_hash(rows, rec["equality_mode"]),
        }
    return oracle


if __name__ == "__main__":
    con = _connect()
    try:
        oracle = freeze_live(con)
    finally:
        con.close()

    with open(OUT_PATH, "w") as fh:
        json.dump(oracle, fh, indent=2, default=str)

    print(f"oracle -> {OUT_PATH}\n")
    for rec in GOLD_CROSS_DP_LIVE:
        qid = rec["id"]
        o = oracle[qid]
        tag = (
            f"  [abstain {','.join(rec['expect_abstain'])}]"
            if rec.get("expect_abstain")
            else ""
        )
        disc = "  [DISCRIMINATOR]" if rec.get("is_discriminator") else ""
        if "skipped" in o:
            print(f"{qid} ({rec['category']}){disc} -> SKIPPED: {o['skipped']}")
            continue
        print(
            f"{qid} ({rec['category']}, {rec['equality_mode']}){tag}{disc} "
            f"rows={len(o['rows'])} hash={o['row_hash'][:16]}"
        )
        for r in o["rows"][:6]:
            print(f"    {r}")
        if len(o["rows"]) > 6:
            print(f"    ... (+{len(o['rows']) - 6} more)")

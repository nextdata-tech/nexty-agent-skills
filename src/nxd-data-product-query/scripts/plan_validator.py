"""Strict mode — verify a query plan against the MCP gateway + relations.

Pure local validator. No network. Loads the plan written by the LLM, the
gateway catalogue from ``mcp_gateway.py``, and the relations bundle from
``semantic_relations.py``, then runs five checks:

  1. no_direct_access    — no step carries direct_sql, presigned_url, or
                           http_request fields (Rule 1).
  2. unknown_endpoint    — every steps[*].dp matches a DP that has at
                           least one MCP endpoint in the gateway (Rule 1).
  3. unknown_function    — every (steps[*].dp, steps[*].mcp_function)
                           pair appears in gateway.function_index (Rule 4).
  4. unknown_relationship— every relationships_used[*] matches an entry
                           in the relations bundle by from_dp/from_model/
                           to_dp/to_model/kind (Rule 2).
  5. unsupported_param   — every steps[*].request value is bound to one
                           of: a provenance phrase, an output of a
                           depends_on step, or a relationships_used entry.

Emits:

    {
      "passed": true|false,
      "checks": [{"name": "...", "status": "pass|skip", "detail": "..."}],
      "failures": [{"check": "...", "step_id": "s1", "detail": "..."}]
    }

CLI:

    python3 plan_validator.py --plan plan.json \
        --gateway gateway.json --relations relations.json \
        --out validation.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


_DIRECT_ACCESS_FIELDS = ("direct_sql", "presigned_url", "http_request", "raw_db", "raw_http")


def _load(path: str, label: str) -> Any:
    try:
        return json.loads(Path(path).read_text())
    except (OSError, json.JSONDecodeError) as exc:
        sys.exit(f"cannot read {label} file {path}: {exc}")


def _check_no_direct_access(plan: dict) -> list[dict]:
    fails: list[dict] = []
    for step in plan.get("steps") or []:
        bad = [f for f in _DIRECT_ACCESS_FIELDS if f in step]
        if bad:
            fails.append(
                {
                    "check": "no_direct_access",
                    "step_id": step.get("id"),
                    "detail": f"step carries non-MCP field(s): {bad}",
                }
            )
    return fails


def _check_endpoints(plan: dict, gateway: dict) -> list[dict]:
    dps_with_mcp = {
        e.get("dp_full_name")
        for e in gateway.get("endpoints") or []
        if e.get("dp_full_name") and not e.get("error")
    }
    fails: list[dict] = []
    for step in plan.get("steps") or []:
        dp = step.get("dp")
        if dp and dp not in dps_with_mcp:
            fails.append(
                {
                    "check": "unknown_endpoint",
                    "step_id": step.get("id"),
                    "detail": f"dp {dp!r} has no healthy MCP endpoint in the gateway",
                }
            )
    return fails


def _check_functions(plan: dict, gateway: dict) -> list[dict]:
    fn_pairs = {(f.get("dp"), f.get("tool")) for f in gateway.get("function_index") or []}
    fails: list[dict] = []
    for step in plan.get("steps") or []:
        dp = step.get("dp")
        fn = step.get("mcp_function")
        if not dp or not fn:
            fails.append(
                {
                    "check": "unknown_function",
                    "step_id": step.get("id"),
                    "detail": "step is missing dp or mcp_function",
                }
            )
            continue
        if (dp, fn) not in fn_pairs:
            fails.append(
                {
                    "check": "unknown_function",
                    "step_id": step.get("id"),
                    "detail": f"(dp={dp!r}, function={fn!r}) is not in gateway.function_index",
                }
            )
    return fails


def _rel_key(r: dict) -> tuple:
    return (
        r.get("from_dp"),
        r.get("from_model"),
        r.get("to_dp"),
        r.get("to_model"),
        r.get("kind"),
    )


def _check_relationships(plan: dict, relations: dict) -> list[dict]:
    known = {_rel_key(r) for r in relations.get("relationships") or []}
    fails: list[dict] = []
    for idx, rel in enumerate(plan.get("relationships_used") or []):
        key = _rel_key(rel)
        if not all(key[:5]):
            fails.append(
                {
                    "check": "unknown_relationship",
                    "step_id": f"relationships_used[{idx}]",
                    "detail": "missing required fields (from_dp/from_model/to_dp/to_model/kind)",
                }
            )
            continue
        if key not in known:
            fails.append(
                {
                    "check": "unknown_relationship",
                    "step_id": f"relationships_used[{idx}]",
                    "detail": f"no matching entry in relations bundle for {key}",
                }
            )
            continue
        ev = rel.get("evidence") or {}
        sm_dp = ev.get("semantic_model_dp")
        if sm_dp and sm_dp != key[0] and sm_dp != key[2]:
            fails.append(
                {
                    "check": "unknown_relationship",
                    "step_id": f"relationships_used[{idx}]",
                    "detail": (
                        f"evidence.semantic_model_dp={sm_dp!r} is neither side of the "
                        f"relationship ({key[0]!r}, {key[2]!r})"
                    ),
                }
            )
    return fails


def _check_params(plan: dict) -> list[dict]:
    """Every step.request value must reference a provenance phrase, an
    upstream step's output, a relationships_used entry, or be a literal
    explicitly marked as such."""
    fails: list[dict] = []

    provenance_by_step: dict[str, set[str]] = {}
    for p in plan.get("provenance") or []:
        sid = p.get("step_id")
        param = p.get("param")
        if sid and param:
            provenance_by_step.setdefault(sid, set()).add(param)

    rels_used = plan.get("relationships_used") or []
    rel_aliases = {
        f"relationships_used[{i}]" for i, _ in enumerate(rels_used)
    }

    steps_by_id = {s.get("id"): s for s in (plan.get("steps") or [])}

    for step in plan.get("steps") or []:
        sid = step.get("id")
        req = step.get("request") or {}
        if not isinstance(req, dict):
            continue
        deps = step.get("depends_on") or []
        dep_outputs = {f"$steps.{d}.output" for d in deps}
        dep_outputs |= {f"$steps.{d}" for d in deps}
        prov = provenance_by_step.get(sid, set())
        for param, value in req.items():
            if _is_param_bound(value, param, prov, dep_outputs, rel_aliases, steps_by_id, deps):
                continue
            fails.append(
                {
                    "check": "unsupported_param",
                    "step_id": sid,
                    "detail": (
                        f"request.{param}={value!r} is not bound — provide a "
                        f"provenance entry, a depends_on output ref, or tag "
                        f"a relationships_used entry"
                    ),
                }
            )

    return fails


def _is_param_bound(
    value: Any,
    param: str,
    prov: set[str],
    dep_outputs: set[str],
    rel_aliases: set[str],
    steps_by_id: dict[str, dict],
    deps: list[str],
) -> bool:
    if param in prov:
        return True
    if isinstance(value, str):
        if value in dep_outputs or value in rel_aliases:
            return True
        if value.startswith("$steps."):
            head = value.split(".", 2)[1] if value.count(".") >= 1 else ""
            if head in deps and head in steps_by_id:
                return True
        if value.startswith("$relationships_used["):
            return value.rstrip("]").startswith("$relationships_used[") and value[len("$relationships_used["):-1].isdigit()
        if value.startswith("$literal:"):
            return True
    # Literals tagged inside a dict like {"literal": ...}
    if isinstance(value, dict) and "literal" in value:
        return True
    return False


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--plan", required=True)
    p.add_argument("--gateway", required=True)
    p.add_argument("--relations", required=True)
    p.add_argument("--out", help="Where to write the validation report (default: stdout)")
    args = p.parse_args()

    plan = _load(args.plan, "plan")
    gateway = _load(args.gateway, "gateway")
    relations = _load(args.relations, "relations")

    all_failures: list[dict] = []
    checks: list[dict] = []

    for name, fn in (
        ("no_direct_access", lambda: _check_no_direct_access(plan)),
        ("unknown_endpoint", lambda: _check_endpoints(plan, gateway)),
        ("unknown_function", lambda: _check_functions(plan, gateway)),
        ("unknown_relationship", lambda: _check_relationships(plan, relations)),
        ("unsupported_param", lambda: _check_params(plan)),
    ):
        fails = fn()
        all_failures.extend(fails)
        checks.append(
            {"name": name, "status": "fail" if fails else "pass", "failure_count": len(fails)}
        )

    report = {
        "passed": not all_failures,
        "checks": checks,
        "failures": all_failures,
    }

    serialised = json.dumps(report, indent=2)
    if args.out:
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(serialised)
        print(
            json.dumps(
                {"out": str(out_path), "passed": report["passed"], "failures": len(all_failures)},
                indent=2,
            )
        )
    else:
        print(serialised)


if __name__ == "__main__":
    main()

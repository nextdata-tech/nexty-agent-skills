#!/usr/bin/env python3
"""Runner-side oracle for the incremental transform round-trip.

The judge reads a transcript and can be talked into a verdict. This checker
executes the submitted transform three times against one reused run directory,
carrying the JSON-folded state between runs under a modeled desktop kernel
boundary. It is authoritative about the closure's observed rows and state
trajectory; it does not claim that a live supervisor transaction occurred.

Usage (the harness supplies both paths):

    check_incremental_state.py --fixtures <scenario/fixtures> --root <workspace>

Exit 0 with ALL CHECKS PASSED, or non-zero with the failing check named.
"""

from __future__ import annotations

import argparse
import inspect
import json
import shutil
import sys
import tempfile
import types
from dataclasses import dataclass, field
from pathlib import Path

BASE_ROWS = 100
DELTA_ROWS = 40
GENERIC_STATE_KEY = "__nxd_generic__"


@dataclass
class DuckDbOutput:
    path: str
    schema: str
    model_tables: dict
    models: dict = field(default_factory=dict)


class FakeTransformState(dict):
    """Model the current MultiModelTransformState persistence boundary."""

    def __init__(self, declared, prior=None):
        prior = json.loads(json.dumps(prior or {}, allow_nan=False))
        self._declared = list(declared)
        self._bags = {m: dict(prior.get(m, {})) for m in self._declared}
        self._generic = dict(prior[GENERIC_STATE_KEY]) if GENERIC_STATE_KEY in prior else None
        self._bound = self._declared[0] if len(self._declared) == 1 else None
        if self._bound is not None:
            dict.__init__(self, self._bags[self._bound])
            self._bags[self._bound] = self
        else:
            dict.__init__(self)
        self.dropped_flat_write = False

    def for_model(self, name):
        if name not in self._bags:
            raise KeyError(f"unknown model {name!r}; declared: {sorted(self._bags)}")
        if name == self._bound:
            return self
        return self._bags[name]

    def generic(self):
        if self._generic is None:
            self._generic = {}
        return self._generic

    def models(self):
        return list(self._declared)

    def __setitem__(self, key, value):
        if self._bound is None:
            self.dropped_flat_write = True
        dict.__setitem__(self, key, value)

    def persist(self):
        snapshot = {m: dict(self._bags[m]) for m in self._declared}
        if self._generic is not None:
            snapshot[GENERIC_STATE_KEY] = dict(self._generic)
        return json.loads(json.dumps(snapshot, allow_nan=False))


def install_fake_nxd():
    nxd = types.ModuleType("nxd")
    core = types.ModuleType("nxd.core")
    ctx = types.ModuleType("nxd.core.context")
    ctx.DuckDbOutput = DuckDbOutput
    dp = types.SimpleNamespace(
        on_transform=lambda *a, **k: (lambda fn: fn), main=lambda: None
    )
    nxd.data_product, nxd.core, core.context = dp, core, ctx
    sys.modules.update({"nxd": nxd, "nxd.core": core, "nxd.core.context": ctx})


def load_transform(dp_root: Path):
    sys.path.insert(0, str(dp_root))
    import transform.main as tm  # noqa: E402

    return tm


def run_once(tm, dp_root: Path, run: Path, prior_state):
    physical = list(tm.PHYSICAL_MODELS)
    out = DuckDbOutput(
        path=str(run / "data.duckdb"),
        schema="main",
        model_tables={m: m for m in physical},
    )
    kwargs = {
        "duckdb": out,
        "secrets": {"csv_source": str((dp_root / "data").resolve())},
    }
    state = None
    if "transform_state" in inspect.signature(tm.ingest).parameters:
        state = FakeTransformState(physical, prior=prior_state)
        kwargs["transform_state"] = state
    marker = run / ".transform-complete"
    marker.unlink(missing_ok=True)
    tm.ingest(**kwargs)

    import duckdb as duckdb_lib

    con = duckdb_lib.connect(out.path, read_only=True)
    counts, distinct = {}, {}
    materialized = set()
    actual_tables = {row[0] for row in con.execute("SHOW TABLES").fetchall()}
    for model in physical:
        if model not in actual_tables:
            continue
        materialized.add(model)
        counts[model] = con.execute(
            f"SELECT COUNT(*) FROM main.{model}"
        ).fetchone()[0]
        if model == "events":
            distinct[model] = con.execute(
                "SELECT COUNT(DISTINCT event_id) FROM main.events"
            ).fetchone()[0]
    con.close()
    return {
        "counts": counts,
        "distinct": distinct,
        "materialized": sorted(materialized),
        "marker": marker.exists(),
        "state": state.persist() if state is not None else None,
        "dropped_flat_write": state.dropped_flat_write if state else False,
        "declares_state": state is not None,
    }


def _scalar_entries(state):
    """Return stable bag/key paths, so the same cursor is checked each run."""
    entries = {}
    for bag_name, bag in (state or {}).items():
        if not isinstance(bag, dict):
            continue
        for key, value in bag.items():
            if type(value) in (int, float, str):
                entries[f"{bag_name}.{key}"] = value
    return entries


def _has_cursor_trajectory(*states):
    paths = set(_scalar_entries(states[0]))
    for state in states[1:]:
        paths &= set(_scalar_entries(state))
    return any(
        [_scalar_entries(state)[path] for state in states] == [BASE_ROWS, BASE_ROWS, BASE_ROWS + DELTA_ROWS]
        for path in paths
    )


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--fixtures", required=True, type=Path)
    ap.add_argument("--root", required=True, type=Path)
    args = ap.parse_args()

    dp_root = args.root / "data_product"
    if not dp_root.is_dir():
        candidates = [p.parents[1] for p in args.root.rglob("transform/main.py")]
        if not candidates:
            print("FAIL no-closure: no transform/main.py under the workspace")
            return 1
        dp_root = candidates[0]

    failures = []
    install_fake_nxd()
    try:
        tm = load_transform(dp_root)
    except Exception as exc:  # noqa: BLE001 - closure import is verdict evidence
        print(f"FAIL import: transform/main.py raised {type(exc).__name__}: {exc}")
        return 1

    if "transform_state" not in inspect.signature(tm.ingest).parameters:
        print("FAIL declares-transform-state: ingest() takes no transform_state "
              "parameter, so no cursor can survive a run boundary")
        return 1

    run = Path(tempfile.mkdtemp())

    def attempt(label, prior):
        try:
            return run_once(tm, dp_root, run, prior)
        except Exception as exc:  # noqa: BLE001 - closure fault is a verdict
            print(f"FAIL {label}: the transform raised {type(exc).__name__}: {exc}")
            return None

    r1 = attempt("run1-completes", None)
    if r1 is None:
        return 1
    if not r1["declares_state"]:
        failures.append("declares-transform-state: the transform did not accept the "
                        "kernel transform_state argument")
    if r1["dropped_flat_write"]:
        failures.append("for-model-addressing: transform_state was indexed FLAT; "
                        "use for_model() or generic() for a multi-model closure")
    if r1["counts"].get("events") != BASE_ROWS:
        failures.append(f"run1-lands-full-history: expected {BASE_ROWS} events on "
                        f"the first run, found {r1['counts'].get('events')}")
    if r1["distinct"].get("events") != BASE_ROWS:
        failures.append("run1-distinct-events: the first run did not land one row "
                        "for each initial event_id")
    if not r1["marker"]:
        failures.append("run1-marker: .transform-complete was not touched")

    r2 = attempt("cursor-survives-rerun", r1["state"])
    if r2 is None:
        return 1
    if r2["counts"].get("events") != BASE_ROWS:
        got = r2["counts"].get("events")
        why = ("the cursor did not survive the fold and the whole export was "
               "re-appended" if got and got > BASE_ROWS else
               "the table was rewritten instead of remaining unchanged")
        failures.append(f"cursor-survives-rerun: expected {BASE_ROWS} events, "
                        f"found {got} — {why}")
    if r2["distinct"].get("events") != BASE_ROWS:
        failures.append("run2-distinct-events: the unchanged rerun introduced "
                        "duplicate or missing event_ids")
    if not r2["marker"]:
        failures.append("run2-marker: .transform-complete was not touched")

    delta_src = args.fixtures / "delta" / "part-0003.csv"
    if not delta_src.exists():
        print(f"FAIL harness: delta fixture missing at {delta_src}")
        return 1
    target = dp_root / "data" / "events" / "part-0003.csv"
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(delta_src, target)

    r3 = attempt("delta-run-completes", r2["state"])
    if r3 is None:
        return 1
    expected_total = BASE_ROWS + DELTA_ROWS
    if r3["counts"].get("events") != expected_total:
        failures.append(f"delta-lands-once: expected {expected_total} events after "
                        f"the delta, found {r3['counts'].get('events')}")
    if r3["distinct"].get("events") != expected_total:
        failures.append("run3-distinct-events: the delta was not landed exactly once")
    if not _has_cursor_trajectory(r1["state"], r2["state"], r3["state"]):
        failures.append("cursor-trajectory: no persisted bag/key follows 100 -> 100 -> 140")
    if not r3["marker"]:
        failures.append("run3-marker: .transform-complete was not touched")

    for failure in failures:
        print(f"FAIL {failure}")
    if failures:
        return 1
    print(f"run1={r1['counts']} run2={r2['counts']} run3={r3['counts']} "
          f"state={r3['state']}")
    print("ALL CHECKS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

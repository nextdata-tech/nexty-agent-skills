"""A REAL NXD transform that runs the field mapper. This one executes.

    python3 examples/e2e/transform_main.py            # replay, no API calls
    .venv-live/bin/python examples/e2e/transform_main.py --live

The difference from `run_e2e.py`, and the reason both exist:

- `run_e2e.py` proves the DATA CHAIN — dlt lands rows, the mapper judges them,
  the gate decides, dlt lands the judgements. It calls `map_inputs` directly.
- **this file** proves the PLATFORM ENTRYPOINT — the closure is registered with
  `@data_product.on_transform()` and invoked by nxd's own
  `data_product.run_transform(...)`, so nxd's registry, argument binding, and
  task wrapper are all exercised for real rather than stubbed.

What is genuinely real here:

- `nxd.core` v0.41.x is imported and drives the call. The `ExecutionContext` is
  built by `ExecutionContext.from_json`, nxd's own deserializer — not a stub
  object shaped to look like one. If nxd changes the context schema, this file
  fails to construct rather than quietly drifting.
- `TransformTask` resolves the `context` kwarg through
  `FullContextArgumentProvider`, the same provider a platform run uses.
- dlt and duckdb are real, and so is the whole mapper.

- **The output port is a real `DuckDbOutput`**, resolved from the context by
  nxd's `TransformInputOutputPortArgumentProvider` and injected into the closure
  BY PARAMETER NAME — the same binding a platform run performs. The closure
  reads `duckdb.path`, `duckdb.schema` and `duckdb.model_tables` from it rather
  than from the environment, and asks `full_table_name()` for every physical
  table name.

  This needs the monorepo source on `PYTHONPATH`, because the installed wheel is
  v0.41.26 and `local/duckdb/storage` did not exist yet there. `bootstrap.py`
  handles it; see the README.

What is NOT real, stated plainly:

- No kernel, no transaction, no `transform_state`, no provisioning. The context
  is hand-built rather than produced by the kernel, so this proves the
  ENTRYPOINT and the STORAGE BINDING, not the orchestration that would supply
  them in a cluster.
- The DuckDB file is created by this script, not provisioned by a driver.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent.parent))

# BEFORE any `import nxd`. The installed wheel predates `local/duckdb/storage`,
# so without this the DuckDbOutput port cannot be bound at all and the run would
# prove strictly less while looking identical.
from bootstrap import describe, use_monorepo_nxd  # noqa: E402

use_monorepo_nxd()

import dlt  # noqa: E402
import duckdb as duckdb_lib  # noqa: E402

from nxd import data_product  # noqa: E402
from nxd.core.context import DuckDbOutput  # noqa: E402

from field_mapper import (  # noqa: E402
    evaluate_coverage,
    map_inputs,
    resolve,
)
from field_mapper.errors import FieldMapperError  # noqa: E402
from field_mapper.records import reviews_from_csv  # noqa: E402

# The data-chain pieces are imported from the sibling runner rather than
# duplicated: two copies of the fixture data and the replay caller would drift,
# and a divergence between them would be invisible until one of them lied.
from run_e2e import (  # noqa: E402
    BASE_MODEL,
    MAPPER_MODELS,
    _EVIDENCE_HINTS,
    _PROPOSAL_HINTS,
    _ReplayCaller,
    _build_grant,
    _build_spec,
    _fake_source_rows,
    _live_caller,
    _mapper_inputs_from_rows,
)

#: Where the closure puts its warehouse. A platform run gets this from the
#: output port; with no port available (see the module docstring) the transform
#: is told through the environment, which is at least explicit.
LIVE_ENV_VAR = "FIELD_MAPPER_E2E_LIVE"


def _context_json(db_path: Path) -> str:
    """The execution context, in nxd's own wire shape.

    A platform run gets this from the kernel with the port resolved by the
    driver. Hand-building it is the one thing still stubbed — but the SHAPE is
    nxd's, parsed by `ExecutionContext.from_json`, and the port is a real
    `local/duckdb/storage` service that nxd materialises into a `DuckDbOutput`.
    A schema change on nxd's side fails here rather than drifting.

    Note `service` is a sibling of `context`, not a key inside it — copied from
    nxd's own `test_context.py` rather than guessed.
    """
    return json.dumps(
        {
            "data_product": "invoice-terms",
            "inputs": [],
            "output_ports": [
                {
                    "name": "duckdb",
                    "service": "local/duckdb/storage",
                    "context": {
                        "type_hint": "DuckDbOutput",
                        "models": [],
                        "data": {
                            "path": str(db_path),
                            "schema": "invoices",
                            # The model -> physical table map the closure reads.
                            # A platform run gets these from the driver; the
                            # transform never hardcodes a table name either way.
                            "model_tables": {
                                m: m for m in (BASE_MODEL,) + MAPPER_MODELS
                            },
                        },
                    },
                }
            ],
        }
    )

#: Set by the closure so the caller can assert on what happened. A platform run
#: would surface this through the task result and the landed tables; here it is
#: how the harness checks the transform did what it claimed.
OUTCOME: dict[str, Any] = {}


@data_product.on_transform()
def ingest(duckdb: DuckDbOutput) -> None:
    """Land invoice documents, judge them with the mapper, land the judgements.

    Registered with nxd's real decorator and invoked by nxd's real
    `run_transform`. The `duckdb` argument is bound BY PARAMETER NAME to the
    output port named `duckdb` in the context, and materialised as a real
    `DuckDbOutput` by nxd's `TransformInputOutputPortArgumentProvider` — the
    same binding a platform run performs. Every physical table name comes from
    `duckdb.model_tables` / `full_table_name()`, never from a literal here.

    The ORDER is the load-bearing part, and it is why this cannot be one
    `pipeline.run`:

        run 1  ->  land base models (the mapper's inputs)
        read   ->  base rows + durable reviews
        map    ->  one call per input, the only network in this closure
        gate   ->  may refuse; if it does, NOTHING from run 2 lands
        run 2  ->  land proposals, evidence, and the wide projection

    A single run would either judge rows that are not landed yet, or land
    judgements before the gate has spoken.
    """
    # Everything physical comes FROM THE PORT.
    db_path = Path(duckdb.path)
    schema = duckdb.schema
    tables = duckdb.model_tables
    live = os.environ.get(LIVE_ENV_VAR) == "1"
    run_dir = db_path.parent

    OUTCOME["port_path"] = duckdb.path
    OUTCOME["port_schema"] = duckdb.schema
    OUTCOME["port_tables"] = dict(duckdb.model_tables)

    os.environ["DLT_DATA_DIR"] = str(run_dir / "dlt-data")
    pipeline = dlt.pipeline(
        pipeline_name="field_mapper_transform",
        pipelines_dir=str(run_dir / "dlt-pipelines"),
        destination=dlt.destinations.duckdb(credentials=str(db_path)),
        dataset_name=schema,
    )

    # ---- run 1: land the mapper's inputs ---------------------------------
    @dlt.resource(name=tables[BASE_MODEL], write_disposition="replace")
    def invoice_documents():
        yield from _fake_source_rows()

    pipeline.run([invoice_documents()])

    # `duckdb_lib`, not `duckdb`: the port argument shadows the library name
    # inside this closure, which is precisely why the import is aliased.
    con = duckdb_lib.connect(str(db_path))
    landed = con.execute(
        f"SELECT invoice_id, vendor, page_text "
        f"FROM {duckdb.full_table_name(BASE_MODEL)} ORDER BY invoice_id"
    ).fetchall()
    con.close()

    # ---- map -------------------------------------------------------------
    spec = _build_spec()
    grant = _build_grant(spec)
    inputs = _mapper_inputs_from_rows(landed)
    caller = _live_caller(spec) if live else _ReplayCaller()

    result = map_inputs(
        inputs,
        spec=spec,
        grant=grant,
        call=caller,
        run_dir=str(run_dir / "mapper"),
    )

    # ---- resolve ---------------------------------------------------------
    reviews_file = HERE / "reviews" / "mapper_reviews.csv"
    reviews = (
        reviews_from_csv(reviews_file.read_text(encoding="utf-8"))
        if reviews_file.exists()
        else []
    )
    resolution = resolve(
        result.proposals,
        reviews,
        result.evidence,
        fields=spec.field_names,
        min_evidence_per_ok_cell=min(
            (f.min_evidence for f in spec.target_fields), default=0
        ),
    )

    # ---- the gate --------------------------------------------------------
    report = evaluate_coverage(
        result.cells,
        max_degrade_share=spec.thresholds.max_degrade_share,
        max_error_rate=spec.thresholds.max_error_rate,
        max_absent_share=spec.thresholds.max_absent_share,
        max_unverified_share=spec.thresholds.max_unverified_share,
        raise_on_block=False,
    )
    try:
        resolution.assert_bijection()
        resolution.assert_value_hashes()
        resolution.assert_cardinality(
            min_rows=spec.cardinality.min_rows,
            max_rows=spec.cardinality.max_rows or len(resolution.row_keys),
        )
    except FieldMapperError as exc:
        report.blocked = True
        report.reasons.append(f"structural assert failed: {exc}")

    OUTCOME["status_counts"] = result.status_counts()
    OUTCOME["blocked"] = report.blocked
    OUTCOME["reasons"] = list(report.reasons)

    if report.blocked:
        # RAISED, not returned. A transform that discovers its output is
        # untrustworthy must fail the task — returning quietly would let the
        # platform mark the run successful with nothing landed, which reads as
        # "no new data" rather than "the build was refused".
        raise RuntimeError(
            "field mapper blocked the build; nothing landed:\n  "
            + "\n  ".join(report.reasons)
        )

    # ---- run 2: land the judgements --------------------------------------
    @dlt.resource(
        name=tables["mapper_proposals"],
        write_disposition="replace",
        columns=_PROPOSAL_HINTS,
    )
    def mapper_proposals():
        yield from (p.as_row() for p in result.proposals)

    @dlt.resource(
        name=tables["mapper_evidence"],
        write_disposition="replace",
        columns=_EVIDENCE_HINTS,
    )
    def mapper_evidence():
        yield from (e.as_row() for e in resolution.evidence)

    @dlt.resource(name=tables["invoice_terms"], write_disposition="replace")
    def invoice_terms():
        yield from resolution.wide_rows

    pipeline.run([mapper_proposals(), mapper_evidence(), invoice_terms()])
    OUTCOME["landed"] = True


def _prove_block() -> int:
    """The gate must REFUSE, and nothing from run 2 may exist when it does.

    A gate that has never been seen to block is not a proven gate. This drives
    the same real `run_transform`, with `max_absent_share` tightened to 0 so the
    one genuinely-absent payment term breaches it, then checks the DATABASE
    rather than the return value: `invoice_documents` (run 1) must be present
    and every judgement table (run 2) must be absent.

    That ordering is the whole reason the closure is two `pipeline.run` calls.
    If the gate ran after publication, this check would find the judgement
    tables sitting there under a build that was refused.
    """
    import dataclasses

    # Patch THIS module's binding, not `run_e2e`'s. `_build_spec` was imported
    # by name at load time, so the closure holds a reference in this module's
    # namespace; rebinding it in run_e2e leaves the closure calling the
    # original. (First attempt did exactly that and the gate silently did not
    # block — a monkeypatch that misses looks identical to a check that passes.)
    _re = sys.modules[__name__]

    run_dir = HERE / "_blockproof"
    shutil.rmtree(run_dir, ignore_errors=True)
    run_dir.mkdir(parents=True)
    db_path = run_dir / "warehouse.duckdb"
    os.environ[LIVE_ENV_VAR] = "0"

    original = _re._build_spec

    def _strict() -> Any:
        spec = original()
        return dataclasses.replace(
            spec,
            thresholds=dataclasses.replace(spec.thresholds, max_absent_share=0.0),
        )

    _re._build_spec = _strict
    print("\n[nxd] run_transform  (block proof: max_absent_share=0)")
    try:
        data_product.run_transform(_context_json(db_path))
        print("  FAIL: the transform returned; the gate did not block")
        return 1
    except RuntimeError as exc:
        print(f"  blocked, as required: {str(exc).splitlines()[0]}")
    finally:
        _re._build_spec = original

    con = duckdb_lib.connect(str(db_path))
    present = {
        r[0]
        for r in con.execute(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = 'invoices'"
        ).fetchall()
    }
    con.close()
    shutil.rmtree(run_dir, ignore_errors=True)

    leaked = sorted(present & set(MAPPER_MODELS))
    print(f"  run-1 table present: {BASE_MODEL in present}")
    print(f"  run-2 tables leaked: {leaked or 'none'}")
    if BASE_MODEL not in present:
        print("  FAIL: run 1 did not land, so this proves nothing about run 2")
        return 1
    if leaked:
        print("  FAIL: a blocked build published judgements")
        return 1
    print("\nOK: the gate refused and NOTHING from run 2 landed.")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Run the mapper as a real nxd transform.")
    ap.add_argument("--live", action="store_true", help="make real API calls")
    ap.add_argument("--keep", action="store_true", help="keep the duckdb file")
    ap.add_argument(
        "--prove-block",
        action="store_true",
        help=(
            "tighten max_absent_share to 0 so the genuinely-absent payment term "
            "breaches it, then assert the transform RAISED and no judgement "
            "table exists"
        ),
    )
    args = ap.parse_args(argv)
    if args.prove_block:
        return _prove_block()

    run_dir = HERE / "_transform_run"
    if run_dir.exists():
        shutil.rmtree(run_dir)
    run_dir.mkdir(parents=True)
    db_path = run_dir / "warehouse.duckdb"
    os.environ[LIVE_ENV_VAR] = "1" if args.live else "0"

    context_json = _context_json(db_path)

    # Which nxd answered decides what a green run proves, so it is printed
    # rather than assumed: on the older wheel the DuckDbOutput binding does not
    # exist and the run would fail rather than silently prove less.
    print(f"\n[nxd] {describe()}")
    print(f"[nxd] run_transform  ({'LIVE' if args.live else 'replay'})")
    try:
        data_product.run_transform(context_json)
    except RuntimeError as exc:
        print(f"\n  TRANSFORM RAISED (the gate refused):\n    {exc}")
        return 2

    print("[nxd] transform returned cleanly")
    # Read back off the PORT the closure was handed, which is the thing being
    # proven: nxd resolved it and injected it by parameter name.
    print(f"      port path:     {OUTCOME.get('port_path')}")
    print(f"      port schema:   {OUTCOME.get('port_schema')}")
    print(f"      port tables:   {sorted(OUTCOME.get('port_tables') or {})}")
    print(f"      status counts: {OUTCOME.get('status_counts')}")

    # ---- assert on what LANDED, not on what the closure said -------------
    con = duckdb_lib.connect(str(db_path))
    print("\n--- landed tables " + "-" * 42)
    problems: list[str] = []
    for model in (BASE_MODEL,) + MAPPER_MODELS:
        try:
            n = con.execute(f"SELECT count(*) FROM invoices.{model}").fetchone()[0]
        except Exception as exc:  # noqa: BLE001
            problems.append(f"{model}: not queryable — {exc}")
            print(f"  FAIL {model}: {exc}")
            continue
        print(f"  {model:<20} {n:>4} row(s)")
        if n == 0:
            problems.append(f"{model}: landed zero rows")

    print("\n--- invoice_terms (wide) " + "-" * 35)
    for row in con.execute(
        "SELECT target_row_key, invoice_ref, total_usd, payment_terms_days "
        "FROM invoices.invoice_terms ORDER BY 1"
    ).fetchall():
        print("  " + " | ".join("" if v is None else str(v) for v in row))
    con.close()

    if not args.keep:
        shutil.rmtree(run_dir, ignore_errors=True)
    else:
        print(f"\nduckdb kept at {db_path}")

    if problems:
        print(f"\nFAILED: {len(problems)} problem(s)")
        for p in problems:
            print(f"  - {p}")
        return 1
    print(
        "\nOK: the mapper ran inside a real nxd transform, invoked by nxd's own "
        "run_transform,\nand its judgements landed."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

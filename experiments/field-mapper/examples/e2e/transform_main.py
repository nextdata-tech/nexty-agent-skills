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

What is NOT real, stated plainly:

- **The output port carries no driver.** `storage_context_type_for_driver` in
  this nxd version has no `duckdb` case, so a DuckDB output port is not
  constructible here at all — the desktop DuckDB path is not in v0.41.26. The
  context therefore declares NO ports and the closure opens duckdb itself.
  A platform run would receive a driver-resolved port and write through it.
- No kernel, no transaction, no `transform_state`, no provisioning. This proves
  the entrypoint and the closure, not the orchestration around them.

So: the transform contract is proven, the storage binding is not. That boundary
is exactly where a cluster would be required, and it is named rather than
papered over.
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
sys.path.insert(0, str(HERE.parent.parent))

import dlt  # noqa: E402
import duckdb  # noqa: E402

from nxd import data_product  # noqa: E402
from nxd.core.context import ExecutionContext  # noqa: E402

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
DB_ENV_VAR = "FIELD_MAPPER_E2E_DB"
LIVE_ENV_VAR = "FIELD_MAPPER_E2E_LIVE"

#: Set by the closure so the caller can assert on what happened. A platform run
#: would surface this through the task result and the landed tables; here it is
#: how the harness checks the transform did what it claimed.
OUTCOME: dict[str, Any] = {}


@data_product.on_transform()
def ingest(context: ExecutionContext) -> None:
    """Land invoice documents, judge them with the mapper, land the judgements.

    Registered with nxd's real decorator and invoked by nxd's real
    `run_transform`. The `context` kwarg is bound by nxd's
    `FullContextArgumentProvider`.

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
    db_path = Path(os.environ[DB_ENV_VAR])
    live = os.environ.get(LIVE_ENV_VAR) == "1"
    run_dir = db_path.parent
    schema = "invoices"
    tables = {m: m for m in (BASE_MODEL,) + MAPPER_MODELS}

    OUTCOME["context_data_product"] = getattr(context, "name", None)
    OUTCOME["ports"] = [getattr(p, "name", None) for p in context.output_ports]

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

    con = duckdb.connect(str(db_path))
    landed = con.execute(
        f"SELECT invoice_id, vendor, page_text FROM {schema}.{BASE_MODEL} "
        f"ORDER BY invoice_id"
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
    os.environ[DB_ENV_VAR] = str(db_path)
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
        data_product.run_transform(
            json.dumps(
                {"data_product": "invoice-terms", "inputs": [], "output_ports": []}
            )
        )
        print("  FAIL: the transform returned; the gate did not block")
        return 1
    except RuntimeError as exc:
        print(f"  blocked, as required: {str(exc).splitlines()[0]}")
    finally:
        _re._build_spec = original

    con = duckdb.connect(str(db_path))
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
    os.environ[DB_ENV_VAR] = str(db_path)
    os.environ[LIVE_ENV_VAR] = "1" if args.live else "0"

    # The context is built by NXD'S OWN deserializer. No output ports: this nxd
    # version has no duckdb storage-context type, so a DuckDB port cannot be
    # constructed (module docstring). Declaring none is honest; declaring a
    # fake one would claim a binding that does not exist.
    context_json = json.dumps(
        {"data_product": "invoice-terms", "inputs": [], "output_ports": []}
    )

    print(f"\n[nxd] run_transform  ({'LIVE' if args.live else 'replay'})")
    try:
        data_product.run_transform(context_json)
    except RuntimeError as exc:
        print(f"\n  TRANSFORM RAISED (the gate refused):\n    {exc}")
        return 2

    print("[nxd] transform returned cleanly")
    print(f"      ports from context: {OUTCOME.get('ports')}")
    print(f"      status counts:      {OUTCOME.get('status_counts')}")

    # ---- assert on what LANDED, not on what the closure said -------------
    con = duckdb.connect(str(db_path))
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

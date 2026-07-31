"""ILLUSTRATIVE ONLY — how the field mapper would sit in a real transform.

**This file does not run.** It is a shape, not a working closure. Two reasons it
cannot run today, both real:

1. `cmd_resolve` is a stub (REVIEW.md CV-3), so the durable-review half of the
   flow below has never executed. The `mapper_reviews` read is written the way it
   *should* work, not the way it does.
2. Nothing has ever been integrated into a transform. Every claim about dlt
   behaviour here is read from `reference/transform-template.md`, not observed.

Read it for the wiring and the ordering. Do not copy it into a data product yet.

---

The shape follows the base-ingest template in
`src/nxd-generate-dp/reference/transform-template.md`: land base models with dlt
readers, append derived models as `@dlt.resource`, one `pipeline.run(...)`, then
the table assert and the completion marker.

What the mapper adds is one derived resource — plus a gate that can refuse to
land at all, which the ordinary template has no equivalent of.

The load-bearing detail is the ORDER. `map_inputs` must see landed rows, which
means the mapper cannot be part of the same `pipeline.run` that lands them. So:

    run 1  ->  land base models (the mapper's inputs)
    read   ->  base rows + durable mapper_reviews
    map    ->  ONE call per input, the only network in the closure
    gate   ->  may refuse; if it does, NOTHING from run 2 lands
    run 2  ->  land proposals, evidence, and the wide projection

Two runs, not one. A single run would either judge rows that are not landed yet,
or land judgements before the gate has spoken.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

# Source-checkout shim goes here, verbatim, per reference/derived-models.md.

import dlt

from nxd import data_product
from nxd.core.context import DuckDbOutput

from field_mapper import (
    Grant,
    MapperInput,
    MapperSpec,
    evaluate_coverage,
    map_inputs,
    resolve,
)
from field_mapper.mapper import SYSTEM_PROMPT
from field_mapper.media import MediaInput
from field_mapper.records import reviews_from_csv
from field_mapper.schema import compile_schema
from field_mapper.transport import Client, RunBudget, TransportConfig, resolve_api_key

# Landed tables promised by spec.py.
BASE_MODELS = ("invoice_documents",)
# The mapper's output is three long-form models plus the wide projection. The
# long form is authoritative; `invoice_terms` is a deterministic projection of it
# (ARCHITECTURE.md "Core inversion").
MAPPER_MODELS = ("mapper_proposals", "mapper_evidence", "invoice_terms")
PHYSICAL_MODELS = BASE_MODELS + MAPPER_MODELS

#: The spec is DATA, not a literal in this file. Design §12: the instruction text
#: IS the rubric, and a dict literal here is policy-as-transform-literal — the
#: defect `derivation-plan.md` names. It lands as a contract file and is loaded.
MAPPER_SPEC_PATH = "contracts/invoice_terms_mapper.json"

#: Durable human review state. It must survive `write_disposition="replace"`, so
#: it can never be one of the tables this transform replaces.
#:
#: UNRESOLVED (design §15 open question 5): where this physically lives is not
#: decided. A CSV under `data/` is regenerable and would be wiped; a separate
#: table is not replace-safe without care. This path is a placeholder for a
#: question with no answer yet.
REVIEWS_PATH = "reviews/mapper_reviews.csv"


@data_product.on_transform()
def ingest(duckdb: DuckDbOutput, secrets: dict[str, Any]) -> None:
    """Land invoice documents, judge them, land the judgements."""
    source_root = Path(secrets["csv_source"])
    run_dir = Path(duckdb.path).parent
    pipelines_dir = run_dir / "dlt-pipelines"
    pipelines_dir.mkdir(parents=True, exist_ok=True)
    os.environ["DLT_DATA_DIR"] = str(run_dir / "dlt-data")

    pipeline = dlt.pipeline(
        pipelines_dir=str(pipelines_dir),
        destination=dlt.destinations.duckdb(credentials=duckdb.path),
        dataset_name=duckdb.schema,
    )

    # ---- run 1: land the mapper's inputs -------------------------------
    # These rows are what the mapper reads. They must exist before it runs, so
    # this is a separate pipeline.run from the one that lands judgements.
    base_readers = []
    for model in BASE_MODELS:
        reader = filesystem(  # noqa: F821 - see template for the import
            bucket_url=str(source_root / model), file_glob="*.csv"
        ) | read_csv()  # noqa: F821
        base_readers.append(reader.with_name(duckdb.model_tables[model]))
    pipeline.run(base_readers, write_disposition="replace")

    # ---- read back what landed ------------------------------------------
    with pipeline.sql_client() as client:
        rows = client.execute_sql(
            f"SELECT invoice_id, pdf_path, page_text "
            f"FROM {duckdb.model_tables['invoice_documents']}"
        )

    # ---- build MapperInputs ---------------------------------------------
    # `media` and `landed_text` are SEPARATE on purpose (mapper.py MapperInput).
    # Media goes to the model; landed_text is the haystack the quote is checked
    # against. Merging them is the circularity the design exists to prevent.
    #
    # Here both are present: the PDF is sent, AND a previously-landed text
    # extraction is supplied, so the substring check can actually run. Drop
    # `landed_text` and every citation becomes `evidence_unverified` — correct
    # values with nothing able to show they are correct (fixture 08).
    inputs = [
        MapperInput(
            input_id=str(invoice_id),
            identity={"invoice_id": invoice_id},
            landed_text=page_text,
            media=[
                MediaInput(
                    media_type="application/pdf",
                    data=Path(pdf_path).read_bytes(),
                    label=f"invoice-{invoice_id}",
                )
            ],
            document_hash=None,
        )
        for invoice_id, pdf_path, page_text in rows
    ]

    spec = MapperSpec.load(MAPPER_SPEC_PATH)
    spec = spec.with_wire_schema(compile_schema(spec))

    # ---- consent ---------------------------------------------------------
    # The grant binds to this exact `mapper_spec_id`. Editing the instruction,
    # the model, or the accepted media types changes the hash and the grant stops
    # matching — deliberately, so a human re-consents to what actually runs.
    #
    # NOT a security boundary (design §9): nothing in the platform enforces it.
    # It is a userland convention plus a Phase D self-check.
    grant = Grant.load("contracts/invoice_terms_grant.json")

    # ---- the only network call in this closure ---------------------------
    client = Client(
        api_key=resolve_api_key(secrets),
        config=TransportConfig.from_spec(spec),
        budget_ledger=None,
        heartbeat=lambda msg: print(f"  . {msg}"),
    )

    def call(*, item, spec, wire_schema, violations=()):
        instruction = spec.instruction
        if violations:
            instruction += "\n\nYour previous answer had these problems:\n" + "\n".join(
                f"- {v}" for v in violations
            )
        return client.call(
            system_prompt=SYSTEM_PROMPT,
            instruction=instruction,
            wire_schema=wire_schema,
            text_inputs=[item.landed_text] if item.landed_text else [],
            media_inputs=item.media,
            input_hash=item.input_id,
        )

    result = map_inputs(
        inputs=inputs,
        spec=spec,
        grant=grant,
        call=call,
        budget=RunBudget(max_calls=500, max_input_tokens=2_000_000,
                         max_output_tokens=500_000, max_usd=25.0),
        run_dir=run_dir / "mapper",
    )

    # ---- resolve: proposals + durable reviews -> effective rows -----------
    # A human override wins over a model proposal. A confirmation whose bound
    # value, input, or spec hash has moved goes STALE and the fresh proposal
    # wins instead — a stale approval is never silently reapplied.
    reviews_file = Path(REVIEWS_PATH)
    reviews = (
        reviews_from_csv(reviews_file.read_text(encoding="utf-8"))
        if reviews_file.exists()
        else []
    )
    resolution = resolve(
        proposals=result.proposals,
        reviews=reviews,
        evidence=result.evidence,
        fields=spec.field_names,
    )
    resolution.assert_bijection()

    # ---- the gate: this can refuse to land anything ----------------------
    # The ordinary template has no equivalent. A systemic failure (missing
    # credential, exhausted budget, cancelled run) or a degrade share above the
    # spec's declared ceiling BLOCKS — and blocking must happen before
    # `pipeline.run`, not after, or a blocked build publishes anyway
    # (REVIEW.md: blocked builds still published).
    report = evaluate_coverage(
        proposals=[cell.proposal for cell in resolution.effective.values()],
        evidence=resolution.evidence,
        thresholds=spec.thresholds,
    )
    if report.blocked:
        raise RuntimeError(
            "field mapper blocked the build; nothing landed:\n  "
            + "\n  ".join(report.reasons)
        )

    # ---- run 2: land the judgements --------------------------------------
    # Long form is authoritative and replace-loaded. `invoice_terms` is DERIVED
    # from the same in-memory bundle, never computed separately — that is what
    # makes it impossible for the wide table and the provenance to disagree.
    @dlt.resource(name=duckdb.model_tables["mapper_proposals"],
                  write_disposition="replace")
    def proposals():
        # `.as_row()` per record — the same call `__main__.py` uses to write CSV.
        yield from (p.as_row() for p in result.proposals)

    @dlt.resource(name=duckdb.model_tables["mapper_evidence"],
                  write_disposition="replace")
    def evidence():
        yield from (e.as_row() for e in resolution.evidence)

    @dlt.resource(name=duckdb.model_tables["invoice_terms"],
                  write_disposition="replace")
    def wide():
        # A property, not a method — built from the same bundle as the sidecar.
        yield from resolution.wide_rows

    pipeline.run([proposals(), evidence(), wide()])

    # NOTE: this is two `pipeline.run` calls, so publication is NOT atomic
    # across them. CONTRACT.md §7.7 requires fault-injection between table
    # resources to prove atomicity; that test does not exist. A crash between
    # run 1 and run 2 leaves landed inputs with no judgements.

    actual = set(pipeline.default_schema.data_table_names())
    expected = {duckdb.model_tables[m] for m in PHYSICAL_MODELS}
    if actual != expected:
        raise RuntimeError(
            f"dlt produced tables {sorted(actual)!r}, expected {sorted(expected)!r}"
        )
    (run_dir / ".transform-complete").touch()


if __name__ == "__main__":
    data_product.main()

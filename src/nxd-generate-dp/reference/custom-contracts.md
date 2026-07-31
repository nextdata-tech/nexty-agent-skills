# Explicit custom contracts in desktop Pocket closures

## Contents

- What belongs in a custom contract
- CSV-first support boundary
- Generated layout and public DSL wiring
- Verification scripts
- Preflight checks

## What belongs in a custom contract

Keep **inferred schema constraints** separate from **explicit user-stated
guarantees**. A type, nullability, key, or enum inferred from profiling belongs
in `models.py` and ordinary `.promise(model)` / source-model checks. It must not
be relabelled as a user guarantee.

Conversely, every explicit must, must-not, cross-field, aggregate,
reconciliation, freshness, or accepted-set invariant is a named custom
contract, even where it partly overlaps an inferred schema constraint. Preserve
the user's wording and give the contract a stable lowercase-hyphenated name.
Examples: `order-total-reconciles`, `accepted-currency`,
`no-future-order-date`, `daily-row-floor`.

Before generating, inventory every contract in `CONTEXT.md` with:

- name and verbatim or faithfully quoted guarantee;
- kind (`input_expectation` or `output_promise`), model, fields, and phase;
- source of authority (`user_stated`, never `inferred` for a custom contract);
- executable rule, failure diagnostic, and whether the closure can actually
  run it.

Do not invent a quality rule merely because a field looks suspicious. Ask for
the missing threshold, accepted set, time zone, tolerance, or reconciliation
population when it changes pass/fail.

## CSV-first support boundary

Pocket supports executable **custom input expectations only for a declared
CSV source-aligned input**. Every Pocket source-aligned input — custom or not
— must use `.source(_csv)`, where `_csv` binds exactly to
`/infra-profile/desktop-local#/services/csv-source`. That unlabeled service
uses `nxd:local/file/storage:0.1.0` and is also the transform secret via
`.secrets([_csv])`. Labeled CSV services are supported only as transform
secrets on this runtime; do not bind one through `.input(...).source(...)`.

The input expectation receives `LocalFileInput` and runs **before** the DLT
transform. It reads only its declared `model_paths` from the pinned export.
DLT separately loads that same export during the transform; a verifier does
not receive a DLT loader or connection context.

For a true database or API source, do not pretend the same local runtime can
run a custom input expectation. Explain that input custom verification is not
supported on the CSV-first Pocket path and either obtain a CSV export or omit
the executable expectation. Never emit a decorative script that is not wired
to an input.

An output promise may be generated for another connector only when the actual
output storage and contract compute context are known to support the verifier.
State that runtime dependency in `CONTEXT.md`; otherwise explain the gap rather
than claiming the promise will execute.

## Generated layout and public DSL wiring

Add one script per named contract, only when its inventory entry is nonempty:

```
contracts/
├── expectations/
│   └── accepted-currency.py       # exactly one CSV input verifier
└── promises/
    └── order-total-reconciles.py  # exactly one DuckDB output verifier
```

Do not create a `contracts/` directory, placeholder script, or empty
`__init__.py` without an explicit custom contract. A `script(...)` executes the
whole file and the custom name does not select one function, so sharing one
phase-wide script can run unrelated checks. Do not duplicate the ordinary
schema promises: every physical output model still keeps `.promise(model)`.

For a CSV input, define `_csv` and `_compute` once in `spec.py`:

```python
_csv = "/infra-profile/desktop-local#/services/csv-source"
_compute = "/infra-profile/desktop-local#/services/python-compute"
```

The transform explicitly uses one host-owned trigger:

```python
.transform(
    script("transform/main.py")
    .compute(_compute)
    .secrets([_csv])
    .when(simple_sensor(startup=False, when="any"))
)
```

Attach an input expectation to the declared source-aligned CSV input before
the transform. Attach an output promise to the DuckDB output after the
transform, while keeping its schema promise:

```python
.input(
    "orders-source",
    source_aligned_input()
    .source(_csv)
    .config({"model_paths": {"orders": "orders/orders.csv"}})
    .expectation(
        custom("accepted-currency")
        .description("User-stated: currency must be EUR or USD.")
        .model(orders)
        .verify(script("contracts/expectations/accepted-currency.py").compute(_compute))
    ),
)
.output(
    data_product_output()
    .promise(orders)
    .promise(
        custom("order-total-reconciles")
        .description("User-stated: output line totals reconcile to order totals.")
        .model(orders)
        .verify(script("contracts/promises/order-total-reconciles.py").compute(_compute))
    )
    .port("duckdb", storage(_duckdb))
)
```

`compute()` is called on the `script(...)` verifier spec, inside
`verify(...)`; `custom(...).verify(...).compute(...)` is not a valid chain.
Use each name exactly once across input expectations and output promises.

The profile declares:

```yaml
- name: csv-source
  driver: nxd:local/file/storage:0.1.0
  attributes: []
```

Keep `csv-source-path` relative. It selects the pinned export root; it is not
a secret value and no absolute host path may enter the closure.
Each CSV source-aligned input also declares `model_paths` relative to that
root, one exact `model: model/model.csv` mapping per attached model. The local
file context uses this mapping; do not scan a root directory or hard-code a
path inside a verifier.

## Verification scripts

Each script has exactly one `@data_product.on_verify()` verifier and ends with
`if __name__ == "__main__": data_product.verify()`. It must be parseable and
has one small `verify` function for its named custom contract; make its
diagnostics name the contract, model, and observed/expected values.

Use concrete runtime contexts. A CSV expectation takes `LocalFileInput` from
`nxd.core.context`, reads only `source.path_for("model")` with `csv.DictReader`,
and returns `VerifyResult(VerifyResultEnum.FAILED, context)` or
`VerifyResult(VerifyResultEnum.PASS, context)`. An output promise takes
`DuckDbOutput`, resolves its table through `output.full_table_name("model")`,
opens `output.path` read-only with `duckdb`, and returns the same result type.
The current enum values are `PASS`, `WARNING`, and `FAILED`; use `FAILED` for a
broken user guarantee. A bare `pass`, `...`, or unconditional PASS is a
decorative verifier and fails preflight.

Verifiers only inspect their supplied input/output context and return the
runtime's supported pass/fail result. They never mutate tables, repair rows,
call an LLM, hide a failure behind a warning, embed secrets, or resolve a path
outside the closure. An aggregate, reconciliation, or freshness check must use
the runtime context actually supplied by the corresponding contract phase; if
that context cannot provide the needed rows or clock, record it as unsupported
instead of writing a fake check.

## Preflight checks

The closure self-check must fail when any custom-contract invariant is broken:

- a referenced `contracts/**/*.py` file is absent, decorative, outside the
  closure, cannot be parsed, has anything other than one registered verifier,
  or does not invoke `data_product.verify()` under its main guard;
- a custom contract has no unique name, description, model, or verifier;
- any Pocket source-aligned input is not `.source(_csv)` with `_csv` bound to
  the exact unlabeled desktop-local `csv-source`, or an input contract is not
  attached to that declaration;
- an output contract is not attached to the DuckDB output alongside ordinary
  `.promise(model)`;
- the verifier script path escapes the closure or does not export the expected
  callable; or
- a contract script or profile carries a secret or absolute external path.

The self-check remains structural/offline. A pass proves the generated closure
is parseable and wired, not that a live Desktop contract execution succeeded.

# Scenario: Generate a multi-source labeled CSV closure

The workspace contains three CSV export roots and a small model brief:

- `source-orders/` — an `orders` export with rows;
- `source-users/` — a `users` export with rows; and
- `source-archive/` — an `archive` export with headers but no rows.

The first two are distinct instances of the same CSV connector type and must
remain distinguishable at runtime. The archive export is deliberately empty;
it must not become a promised physical model or a runtime input that makes the
closure fail during pinning.

## Task for the agent

Read `BRIEF.md`, `inferred_model.json`, and all three export shapes before
authoring. Build the complete Python-only NXD desktop closure the brief asks
for, with the `orders` and `users` sources labeled exactly as requested. Keep
the supplied non-empty CSV bytes unchanged, use relative connector paths, and
make the transform read both labeled roots from the pinned execution root.
Author the closure directly in the workspace root: `spec.py`, `models.py`,
`infra-profile.yaml`, `requirements.txt`, `transform/main.py`, the two
`csv-source-*-path` files, `companion-files`, and the `data-*/` trees must all
be rooted there. Do not put the finished closure under a `data_product/`
subdirectory.

Consult the installed `nxd-generate-data-product` multi-source guidance for the
manifest, runtime floor, and pinning contract. Render the required `README.md`
reopen recipe, including the concrete `companion-directory-probe` compatibility
precondition and the known implementation provenance.
The finished closure must be safe for a compatible supervisor to pin and for
the transform to run after pinning. Work
autonomously; no user is available to answer a delivery question.

In the final response, inventory the authored closure files, identify the two
labeled source roots and the empty source decision, and report only checks you
actually ran.

## Success checks

The eval grades the landed closure and an authoritative runner-side structural
check. It models the declared directory-copy shape; it does not invoke a live
supervisor. The closure must preserve both non-empty labeled roots through the
declared companion-file channel, omit the empty label, keep the declarations
relative and non-overlapping, document the compatible runtime floor, and make
the transform resolve the pinned roots rather than an authoring checkout. The
closure must still use the ordinary Python-only desktop shape and
label-specific CSV connector paths.

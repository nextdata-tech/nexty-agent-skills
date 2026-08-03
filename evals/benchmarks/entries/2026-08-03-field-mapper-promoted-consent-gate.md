---
id: 2026-08-03-field-mapper-promoted-consent-gate
date: 2026-08-03
label: "nxd-generate-data-product: field-mapper promoted, gated on recorded consent"
plugin_version: 0.34.0
status: NO_EVAL
scenarios: []
record: null
---
# Benchmark — nxd-generate-data-product: field-mapper promoted, gated on recorded consent

## Notes

No public scenario builds a closure that vendors the field-mapper harness, so no
scenario can distinguish this change. Authoring one to produce a figure would
make the evidence less trustworthy, not more, which is why this entry carries no
arm rather than a manufactured number.

What shipped: the harness moves out of `experiments/` into
`src/nxd-generate-data-product/mapper/`, and a new self-check phase — Phase G,
the consent gate — fails a closure that vendors it without a grant binding the
mapper spec by hash. Phase G runs between Phase E and Phase B, and that
placement is the load-bearing part: Phase B executes the transform, and the
mapper resolves its key with an environment fallback, so a verdict delivered
after Phase B would be a report about consent already spent. Eight `grant.*`
codes enter the diagnostic vocabulary; three are `owner: user` because an agent
cannot consent on a human's behalf.

Before this, `grant.py` named the Phase D self-check as what enforced consent.
Phase D is the policy-boundary gate and has never checked grants, so the module's
one stated enforcement mechanism did not exist. That sentence is now true.

Two defects found in review and fixed here are worth recording, because both were
the gate stating something the closure contradicted. A closure-root module
holding the mapper import passed green while Phase B executed the mapping — the
scan covered only `transform/`. And a grant missing a required key was not
recognised as a grant at all, so the gate reported "contracts/ carries no consent
grant" with the grant on disk, under `owner: user` / `next_action: confirm`,
stopping the loop to ask a human to re-consent over a schema typo.

## Evidence

`evals/tests/test_grant_gate_phase_g.py` covers the gate over the extracted
block. `evals/tests/test_desktop_custom_contract_checker.py` carries three tests
that drive the **real** `scripts/self_check.py` end to end — the distinction
matters, because the extracted-block harness stubs `diag`/`finish`/`close_stage`
and would hide a `KeyError` from an unregistered code. Those three cover
deny-without-grant (exit 1 with `grant.missing`, and no Phase B output, which is
what proves the ordering), green-with-matching-grant (a gate that can only deny
is indistinguishable from a broken one), and the closure-root module case.

`test_real_self_check_denies_a_mapper_imported_from_a_closure_root_module` was
**verified to fail against the previous implementation**: with the scan reverted
to `transform/`-only it returns 0, reproducing the bypass. The malformed-grant
cases in `test_gate_agrees_with_grant_py_on_malformed_grants` were verified the
same way, and that check has a trap worth naming — the test executes the fenced
copy in `src/nxd-generate-data-product/reference/self-check.md`, not
`scripts/self_check.py`, so reverting only the script leaves it passing and
proves nothing.

The root glob is deliberately non-recursive, so a root *subpackage* still evades
the gate; that residual is recorded in the "What Phase G cannot see" section
rather than left for a reader to discover.

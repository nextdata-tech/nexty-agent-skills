"""Deterministic checks for the derive-models-from-questions scenario.

This checker exists because no generic structural check can know that a refund
should net against its charge. That is a semantic fact about the data, and the
only artifact that can hold it is ground truth computed from the seeded export.

`truth.json` is a RUNNER-SIDE fixture: it never enters the agent workspace. It
carries both the correct netted totals and the exact totals a closure produces
when it forgets to net, so a failure can name the bug instead of only reporting
a mismatch.

CURRENCY STANCE. No exchange rate appears anywhere in the source export, so
there is no single correct cross-currency total and this checker does not
assert one. Truth is stored PRE-FX and PER-CURRENCY; the accepted totals are
composed from whichever stance the closure disclosed:

  * unconverted -- no FX model landed, amounts stay in source currency. Rates
    are all treated as 1, i.e. the mixed-unit sum.
  * converted -- an FX model is landed as data and parsed for its rates, so the
    gate is RATE-AGNOSTIC: 1.27/1.08 and 1.30/1.10 both pass, because the
    checker recomputes the expected total from the closure's own landed rates.

Both stances pass on correct arithmetic. What is gated is DISCLOSURE, not which
choice was made: a closure that silently invents a rate, or silently declines to
convert, fails. Refusing to fabricate a rate is a legitimate answer here and the
fixture must not punish it.

SCOPE. Truth still bakes in the seeded merchant->category mapping
(COGS={AWS, Anthropic, OpenAI}; opex={Deel, Figma, Lufthansa, Monzo, WeWork}).
A closure that classifies differently -- e.g. Anthropic as opex -- fails the
totals gate even if internally consistent. That is a pre-existing property of
this scenario, noted here so such a failure is diagnosable rather than baffling.

Run from the closure root with the fixtures directory passed in:

    python check_derived_closure.py --fixtures <path-to-fixtures>
"""

from __future__ import annotations

import argparse
import ast
import csv
import json
import re
import sys
from decimal import Decimal
from pathlib import Path

FAILURES: list[str] = []
PASSES: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> bool:
    (PASSES if ok else FAILURES).append(name if ok else f"{name}: {detail}".rstrip(": "))
    return ok


def model_constants(transform_src: str) -> dict[str, tuple[str, ...]]:
    """Read BASE_MODELS / DERIVED_MODELS / PHYSICAL_MODELS without importing."""
    tree = ast.parse(transform_src)
    out: dict[str, tuple[str, ...]] = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign) or len(node.targets) != 1:
            continue
        target = node.targets[0]
        if not isinstance(target, ast.Name) or not isinstance(node.value, ast.Tuple):
            continue
        values = [e.value for e in node.value.elts if isinstance(e, ast.Constant)]
        if len(values) == len(node.value.elts):
            out[target.id] = tuple(values)
    return out


def assert_functions(transform_src: str) -> list[ast.FunctionDef]:
    """Every module-level function whose name marks it as an invariant check."""
    tree = ast.parse(transform_src)
    return [
        n
        for n in ast.walk(tree)
        if isinstance(n, ast.FunctionDef)
        and (n.name.startswith("_assert") or n.name.startswith("assert_"))
    ]


def raises_runtime_error(fn: ast.FunctionDef) -> bool:
    return any(isinstance(n, ast.Raise) for n in ast.walk(fn)) or any(
        isinstance(n, ast.Assert) for n in ast.walk(fn)
    )


def reads_source_independently(fn: ast.FunctionDef, transform_src: str) -> bool:
    """An assert that only restates the transform's arithmetic proves nothing.

    Heuristic: the function must take a parameter carrying source rows, or call
    a source-reading helper. Restating a computed total against itself does not
    involve either.
    """
    # Match on the ROLE the parameter plays, not one naming fashion. A closure
    # that names its source rows `txns` re-reads the source exactly as much as
    # one that names them `source_rows`; an earlier version of this heuristic
    # false-negatived a correct closure for calling them `txns`.
    param_names = {a.arg for a in fn.args.args}
    SOURCE_HINTS = ("source", "raw", "src", "txn", "record", "input", "base", "orig")
    # `derived`/`landed`/`out` name the OUTPUT side. A parameter carrying one of
    # those is not evidence the source was re-read -- an earlier version of this
    # heuristic included the bare hint "row", which matched `derived_rows` and
    # let a self-referential assert count as source-anchored.
    DERIVED_HINTS = ("derived", "landed", "output", "out_", "result", "computed")
    for p in param_names:
        low = p.lower()
        if any(h in low for h in DERIVED_HINTS):
            continue
        if any(h in low for h in SOURCE_HINTS):
            return True
    called = {
        n.func.id
        for n in ast.walk(fn)
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
    }
    return any("read" in c and "source" in c for c in called)


def reconciles_a_measure(fn: ast.FunctionDef) -> bool:
    """Tier 2: does this assert actually constrain a MEASURE total?

    Being source-anchored is not enough. A closure can re-read the source, count
    rows, confirm every row landed in a bucket, and still ship a measure that is
    wrong by exactly the rows it forgot to net — that is the failure this
    scenario exists to catch. The assert has to sum something.

    Deliberately does not require `Decimal`: a float reconciliation is weaker
    but still catches the bug. The skill asks for `Decimal`; the judge checks
    that. This checks the invariant is present at all.
    """
    summed = any(
        isinstance(n, ast.Call)
        and (
            (isinstance(n.func, ast.Name) and n.func.id in ("sum", "fsum"))
            or (isinstance(n.func, ast.Attribute) and n.func.attr in ("sum", "fsum"))
        )
        for n in ast.walk(fn)
    )
    if not summed:
        return False
    # An unsigned reconciliation hides the sign error it is supposed to expose:
    # abs(charge) + abs(refund) reconciles against nothing meaningful.
    uses_abs = any(
        isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == "abs"
        for n in ast.walk(fn)
    )
    return not uses_abs


CURRENCY_RE = re.compile(r"^[A-Z]{3}$")
DISCLOSURE_RE = re.compile(r"(?i)(fx|exchange[ -]?rate|currenc)")

# Used only when a landed FX model cannot be parsed, so that an unreadable
# reference CSV degrades to "accept the canonical stances" rather than a hard
# fail on a closure that may well be correct.
FALLBACK_RATES = {"USD": Decimal("1"), "GBP": Decimal("1.27"), "EUR": Decimal("1.08")}


def parse_fx_rates(paths: list[Path]) -> dict[str, Decimal] | None:
    """Recover {currency: rate} from an agent-authored FX CSV.

    Deliberately heuristic: the closure chose the column names, so find the
    column whose values look like ISO currency codes and the first numeric
    column beside it. Returns None when nothing parseable is found.
    """
    for path in paths:
        try:
            rows = list(csv.DictReader(path.open()))
        except (OSError, UnicodeDecodeError, csv.Error):
            continue
        if not rows:
            continue
        cols = [c for c in (rows[0].keys() or []) if c]
        cur_col = next(
            (
                c
                for c in cols
                if all(CURRENCY_RE.match((r.get(c) or "").strip().upper()) for r in rows)
            ),
            None,
        )
        if cur_col is None:
            continue
        for c in cols:
            if c == cur_col:
                continue
            try:
                rates = {
                    (r[cur_col] or "").strip().upper(): Decimal((r[c] or "").strip())
                    for r in rows
                }
            except (ArithmeticError, ValueError, TypeError):
                continue
            if not rates or any(v <= 0 for v in rates.values()):
                continue
            rates.setdefault("USD", Decimal("1"))
            return rates
    return None


def compose(per_currency: dict[str, str], rates: dict[str, Decimal]) -> Decimal | None:
    """Fold a per-currency truth table into one total under `rates`.

    Returns None if the closure's rate table does not cover a currency the
    category actually contains -- that signature is simply not computable, and
    an uncomputable signature must never masquerade as a match.
    """
    total = Decimal("0")
    for currency, amount in per_currency.items():
        rate = rates.get(currency.upper())
        if rate is None:
            return None
        total += Decimal(amount) * rate
    return total


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--fixtures", required=True, type=Path)
    ap.add_argument("--root", default=Path("."), type=Path)
    args = ap.parse_args()

    root: Path = args.root
    truth = json.loads((args.fixtures / "truth.json").read_text())

    # ---- structural: the closure exists at all -------------------------------
    transform_path = root / "transform/main.py"
    if not check("closure:transform-exists", transform_path.is_file(), str(transform_path)):
        print_report()
        return 1
    transform_src = transform_path.read_text(encoding="utf-8")

    for rel in ("spec.py", "models.py", "infra-profile.yaml", "requirements.txt"):
        check(f"closure:{rel}", (root / rel).is_file())

    # ---- the source export must be pristine ----------------------------------
    landed = list(root.glob("data/*/transactions.csv")) + list(root.glob("data/transactions.csv"))
    if check("source:landed", bool(landed), "no landed transactions.csv"):
        src_rows = list(csv.DictReader((args.fixtures / "data/transactions.csv").open()))
        got_rows = list(csv.DictReader(landed[0].open()))
        check(
            "source:byte-preserved",
            len(got_rows) == truth["source_rows"] == len(src_rows),
            f"landed {len(got_rows)} rows, expected {truth['source_rows']}",
        )

    # ---- a derived model must exist ------------------------------------------
    consts = model_constants(transform_src)
    derived = consts.get("DERIVED_MODELS", ())
    check("derived:non-empty", bool(derived), "DERIVED_MODELS is empty or absent")

    # ---- fix 3: assert PRESENCE, and that asserts are source-anchored ---------
    fns = assert_functions(transform_src)
    check("asserts:present", bool(fns), "no _assert_* / assert_* function defined")
    check(
        "asserts:raise",
        bool(fns) and all(raises_runtime_error(f) for f in fns),
        "an assert function neither raises nor asserts",
    )
    check(
        "asserts:source-anchored",
        any(reads_source_independently(f, transform_src) for f in fns),
        "no assert re-reads the source; restating computed arithmetic proves nothing",
    )
    # Tier 2 PRESENCE only. This proves the assert was written, never that it
    # encodes the right intent.
    #
    # An assert proves the derivation matches the shape its author PLANNED; it
    # cannot know whether that plan answers the question. A closure that plans an
    # enrichment, writes a correct enrichment reconciliation, and actually needed
    # a removal passes this check and is still wrong. No structural check can
    # catch that.
    #
    # Verified empirically the other way round: a deliberately sign-stripped
    # closure (absolute values stored, so refunds stop netting) is caught by the
    # signed reconciliation AT BUILD TIME, before any data lands --
    #   RuntimeError: classified_spend EUR total 75614.33 != source -70284.47
    # With that assert disabled the closure builds, prints SELF-CHECK OK, and
    # only the `totals:*` gate below catches it. That is why this scenario
    # carries ground truth at all.
    check(
        "asserts:measure-reconciled",
        any(reads_source_independently(f, transform_src) and reconciles_a_measure(f) for f in fns),
        "no source-anchored assert reconciles a signed measure total; row counts "
        "and bucket totality pass on a closure with wrong numbers",
    )

    # ---- the ruling must not be hardcoded ------------------------------------
    ruling_landed = bool(list(root.glob("data/*categor*/*.csv"))) or bool(
        list(root.glob("data/*merchant*/*.csv"))
    )
    check("ruling:landed-as-model", ruling_landed, "no merchant/category CSV under data/")

    # ---- currency stance: gate DISCLOSURE, never the choice -------------------
    # There is no rate in the export. Converting (with a landed, queryable rate
    # model) and declining to convert (keeping source currency) are BOTH valid.
    # What is not valid is doing either one silently.
    fx_paths = sorted(set(root.glob("data/*fx*/*.csv")) | set(root.glob("data/*rate*/*.csv")))
    converted = bool(fx_paths)
    rates = parse_fx_rates(fx_paths) if converted else None
    unparseable = converted and rates is None
    if converted:
        # Conditional: only meaningful once the closure has chosen to convert.
        check("fx:landed-as-model", True)

    decisions = next(
        (p for p in (root / "DECISIONS.md", root / "decisions.md") if p.is_file()), None
    )
    disclosed = bool(decisions) and bool(
        DISCLOSURE_RE.search(decisions.read_text(encoding="utf-8", errors="replace"))
    )
    # Crude on purpose. A tighter regex generates false failures on legitimate
    # prose; the judge's `decisions-recorded` check is the semantic layer that
    # catches disclosure which is present but gamed.
    check(
        "fx:handling-disclosed",
        disclosed,
        "no DECISIONS.md entry mentions FX / exchange rates / currency. "
        + (
            "Rates were landed and applied, but an unconfirmed ruling must be "
            "recorded as proposed."
            if converted
            else "Amounts were left unconverted, which is defensible, but the "
            "missing rates must be named as a blocker that travels with every "
            "cross-currency answer."
        ),
    )

    # ---- the semantic gate: are the numbers right? ---------------------------
    # This is the check no structural rule can substitute for.
    db = root / "data.duckdb"
    if not db.is_file():
        candidates = list(root.glob("**/*.duckdb"))
        db = candidates[0] if candidates else db
    if not db.is_file():
        check("totals:queryable", False, "no .duckdb produced; cannot verify totals")
        print_report()
        return 1 if FAILURES else 0

    try:
        import duckdb  # noqa: PLC0415
    except ImportError:
        check("totals:queryable", False, "duckdb not importable in checker env")
        print_report()
        return 1 if FAILURES else 0

    con = duckdb.connect(str(db), read_only=True)
    tables = [r[0] for r in con.execute("SHOW TABLES").fetchall()]
    tol = Decimal(truth["tolerance_usd"])

    # Signatures the closure's disclosed stance makes acceptable.
    stance_rates: dict[str, Decimal]
    if not converted:
        stance = "unconverted"
        stance_rates = {c: Decimal("1") for c in ("USD", "GBP", "EUR")}
    elif unparseable:
        stance = "converted (rate model unparseable -- falling back to canonical rates)"
        stance_rates = FALLBACK_RATES
    else:
        stance = f"converted ({', '.join(f'{k}={v}' for k, v in sorted(rates.items()))})"
        stance_rates = rates

    correct = {c: compose(truth["netted_per_currency"][c], stance_rates) for c in ("cogs", "opex")}
    wrong = {
        c: compose(truth["charges_only_per_currency"][c], stance_rates) for c in ("cogs", "opex")
    }

    # A closure may net refunds by EXCLUDING both rows, or by RETAINING the
    # signed pair. Both are arithmetically correct, so probe both aggregations
    # and accept a match on either -- an ABS-only probe fails correct closures
    # of the second kind.
    found_totals: dict[str, list[Decimal]] = {}
    for table in tables:
        cols = [c[1] for c in con.execute(f"PRAGMA table_info('{table}')").fetchall()]
        cat_col = next((c for c in cols if "categor" in c.lower()), None)
        # Substring match, not a fixed whitelist: the closure names its own
        # columns, and `net_amount` / `signed_amount` are as legitimate as
        # `usd_amount`. A whitelist miss shows up as a baffling `totals:found`
        # failure on a correct closure.
        amt_col = next(
            (c for c in cols if "amount" in c.lower() or c.lower() in ("spend", "value")),
            None,
        )
        if not (cat_col and amt_col):
            continue
        rows = con.execute(
            f'SELECT LOWER(CAST("{cat_col}" AS VARCHAR)), '
            f'ABS(SUM("{amt_col}")), SUM(ABS("{amt_col}")) '
            f'FROM "{table}" GROUP BY 1'
        ).fetchall()
        for cat, signed, unsigned in rows:
            if cat in ("cogs", "opex"):
                cands = [Decimal(str(v)) for v in (signed, unsigned) if v is not None]
                if cands:
                    found_totals.setdefault(cat, cands)

    if not check("totals:found", len(found_totals) >= 2, f"got {found_totals or 'nothing'}"):
        print_report()
        return 1

    print(f"currency stance: {stance}")
    for cat in ("cogs", "opex"):
        cands = found_totals.get(cat)
        if not cands:
            check(f"totals:{cat}", False, "not found in any landed table")
            continue
        want, bad = correct[cat], wrong[cat]
        shown = " / ".join(str(c) for c in cands)
        if want is not None and any(abs(c - want) <= tol for c in cands):
            check(f"totals:{cat}", True)
        elif bad is not None and any(abs(c - bad) <= tol for c in cands):
            check(
                f"totals:{cat}",
                False,
                f"got {shown} — this is exactly the charges-only total under the "
                f"{stance} stance. Refunds were never netted. Correct is {want} "
                f"(difference {abs(bad - want)}).",
            )
        elif want is None:
            check(
                f"totals:{cat}",
                False,
                f"got {shown}, but the landed FX model does not cover every "
                f"currency in this category, so no expected total is computable.",
            )
        else:
            check(
                f"totals:{cat}",
                False,
                f"got {shown}; under the {stance} stance the netted total is "
                f"{want} and the charges-only total is {bad} (+/-{tol}). Matching "
                f"neither usually means a rate was applied that is not the one "
                f"landed as data, or the category ruling differs from the seeded one.",
            )

    print_report()
    return 1 if FAILURES else 0


def print_report() -> None:
    for name in PASSES:
        print(f"PASS {name}")
    for name in FAILURES:
        print(f"FAIL {name}")
    print()
    print(f"{len(PASSES)} passed, {len(FAILURES)} failed")
    if not FAILURES:
        print("ALL CHECKS PASSED")


if __name__ == "__main__":
    sys.exit(main())

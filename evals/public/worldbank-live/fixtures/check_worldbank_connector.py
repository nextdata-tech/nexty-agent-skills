"""Deterministic architecture checks for the worldbank-live scenario.

STATIC ONLY — no network, no supervisor, no DuckDB. Everything here is decided
by reading the landed closure, which is what makes it runnable in a scenario
that is `ci_skip`'d for needing both a live desktop supervisor and outbound
access to api.worldbank.org. The payload-shape claims this scenario also makes
(aggregate labelling, the whitespace in two region strings, the 330 rows with a
blank countryiso3code) stay with the judge: they are properties of live remote
data that no offline check can pin.

What it does grade is the one thing the judge reads least reliably — the
INGESTION ARCHITECTURE. `authenticated-api-source-build` learned this the hard
way: its `rest-connector-not-hand-rolled` check was judge-only and prose-graded
until NEX-873, and the measured benchmark
(`evals/benchmarks/entries/2026-08-11-api-source-custom-client-headers.md`)
found agents importing `rest_api_resources` while `requests` fetched every row
beside it. worldbank-live carried the same prose check with the same blind
spot. The gate itself is imported from `evals/tools/api_connector_gate.py`, so
the two scenarios cannot drift.

Run from the closure root with the fixtures directory passed in:

    python check_worldbank_connector.py --fixtures <path-to-fixtures>
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "tools"))
from api_connector_gate import (  # noqa: E402
    declared_endpoints,
    endpoints_not_public,
    find_closure,
    no_hardcoded_url_or_path,
    transform_sources,
    uses_rest_api_resources,
)

# The host and endpoint path prefixes BRIEF.md names. A closure reading
# `secrets["base_url"]` and `secrets["endpoint_<model>"]` carries neither as a
# literal. Prefixes only: `/v2/country` covers the indicator endpoint
# (`/v2/country/all/indicator/NY.GDP.MKTP.CD`) as well, and an endpoint frozen
# at any depth is the same defect.
#
# Deliberately NOT banned: the indicator code `NY.GDP.MKTP.CD` on its own. It
# arrives IN the payload (`indicator.id` on every observation row), so a Tier 1
# assert reconciling the landed rows against it — exactly the kind of check
# this scenario asks for — is correct code, not a frozen endpoint.
WORLDBANK_HOSTS = ("api.worldbank.org",)
WORLDBANK_PATHS = ("/v2/country",)

FAILURES: list[str] = []
PASSES: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> bool:
    (PASSES if ok else FAILURES).append(name if ok else f"{name}: {detail}".rstrip(": "))
    return ok


def print_report() -> None:
    for name in PASSES:
        print(f"PASS {name}")
    for name in FAILURES:
        print(f"FAIL {name}")
    print()
    print(f"{len(PASSES)} passed, {len(FAILURES)} failed")
    if not FAILURES:
        print("ALL CHECKS PASSED")


def reads_flat_secrets(root: Path) -> tuple[bool, str]:
    """Nothing reads `secrets` nested under a service name.

    The supervisor merges every service in `.secrets([...])` into ONE flat map,
    so an `api-source` attribute `base_url` arrives as `secrets["base_url"]` —
    `secrets["api_source"]["base_url"]` raises `KeyError: 'api_source'` at
    transform time, AFTER the credential has already resolved (PR #172, and
    `api-source.md`'s "Credential handling"). A closure with that shape looks
    correct in review and fails only when it runs, which on this scenario means
    a supervisor run nothing in CI performs.

    Deliberately only the NEGATIVE. The obvious companion — "requires a literal
    `secrets['base_url']` read" — accuses a correct closure that copies the map
    first (`cfg = dict(secrets)` … `cfg["base_url"]`) or builds its client
    config generically, and the defect that positive would catch (a host
    frozen into the source) is already `ingestion:no-hardcoded-url-or-path`.
    One defect, one fact: a closure failing both reads as two problems.
    """
    sources = transform_sources(root)
    if not sources:
        return False, "no transform/*.py sources"
    joined = "\n".join(p.read_text(encoding="utf-8", errors="replace") for p in sources)

    nested = re.search(
        r"""secrets\s*(?:\.get\s*\(\s*|\[\s*)['"]api[_-]?source['"]""", joined)
    if nested:
        return False, (
            "transform reads secrets nested under a service name "
            f"({nested.group(0)!r}) — the supervisor merges every service into "
            "ONE flat map, so this raises KeyError: 'api_source' at transform time"
        )
    return True, ""


def main() -> int:
    ap = argparse.ArgumentParser()
    # Accepted and unused: run.py passes it to every deterministic checker, and
    # this one needs no withheld ground truth to decide anything.
    ap.add_argument("--fixtures", required=True, type=Path)
    ap.add_argument("--root", default=Path("."), type=Path)
    args = ap.parse_args()

    root = find_closure(args.root)

    transform_path = root / "transform" / "main.py"
    if not check("closure:transform-exists", transform_path.is_file(), str(transform_path)):
        print_report()
        return 1

    # ---- ingestion architecture -------------------------------------------
    ok, detail = uses_rest_api_resources(root)
    check("ingestion:rest-api-resources-used", ok, detail)

    ok, detail = no_hardcoded_url_or_path(root, WORLDBANK_HOSTS, WORLDBANK_PATHS)
    check("ingestion:no-hardcoded-url-or-path", ok, detail)

    ok, detail = reads_flat_secrets(root)
    check("ingestion:flat-secrets-read", ok, detail)

    # ---- endpoint topology lives in the profile ---------------------------
    endpoints = declared_endpoints(root)
    check(
        "closure:endpoints-in-profile",
        len(endpoints) >= 2,
        f"found {sorted(endpoints)} — this brief names TWO endpoints, so the "
        f"api-source service needs one endpoint_<model> attribute per model in "
        f"infra-profile.yaml, not a companion file beside the transform",
    )
    # An endpoint path is topology, not a credential. Stripped from an export,
    # the recipient gets a closure that cannot run until they work out what the
    # paths were -- a silent failure at their end, not the sender's.
    non_public = endpoints_not_public(root)
    check(
        "closure:endpoints-public",
        not non_public,
        f"{non_public} not marked public: true — an endpoint path is non-secret "
        f"topology and must survive export; redaction is fail-closed, so an "
        f"omitted public: flag strips it just as public: false does",
    )
    check(
        "closure:no-endpoints-companion",
        not (root / "api-source-endpoints").is_file(),
        "closure still ships an api-source-endpoints companion file; the endpoint "
        "map moved to infra-profile.yaml attributes",
    )

    print_report()
    return 1 if FAILURES else 0


if __name__ == "__main__":
    sys.exit(main())

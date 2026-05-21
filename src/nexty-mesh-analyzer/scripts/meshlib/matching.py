"""Candidate input/output matching. Generic — service-type behaviour
(storage kind, per-source-type exclusions) is taken from the injected
Registry, so this module imports no service SDK."""
import json, re

# generic column names carry little matching signal
GENERIC = {"id", "name", "date", "key", "value", "type", "status", "description",
           "created_at", "updated_at", "created_date", "modified_date", "timestamp",
           "created_by", "modified_by"}

# asset / table / directory names too generic to pair on by themselves —
# they count as a match only alongside another signal (schema, lineage)
GENERIC_ASSET_NAMES = {
    "documents", "document", "data", "dataset", "datasets", "table", "tables",
    "output", "outputs", "input", "inputs", "items", "records", "record",
    "export", "exports", "extract", "extracts", "file", "files", "results",
    "dump", "raw", "staging", "tmp", "temp", "main", "default", "sample",
    "samples", "test", "out", "snapshot", "snapshots", "events", "log", "logs",
}

# path/name tokens that imply a pipeline stage
UPSTREAM = {"input", "raw", "landing", "source", "src", "bronze", "ingest"}
DOWNSTREAM = {"output", "curated", "staging", "silver", "gold", "dim", "fact", "mart"}

# keyword -> business domain; the domain with the most keyword hits wins,
# else the candidate is filed under "other"
DOMAIN_KEYWORDS = {
    "sales": ["sales", "revenue", "order", "transaction", "deal", "pipeline", "booking"],
    "marketing": ["marketing", "campaign", "lead", "advert", "promotion", "newsletter"],
    "finance": ["finance", "invoice", "payment", "ledger", "accounting", "billing",
                "budget", "tax", "chargeback"],
    "customer": ["customer", "crm", "contact", "subscriber", "review", "feedback",
                 "support", "ticket"],
    "product": ["product", "catalog", "inventory", "sku", "merchandise", "groceries"],
    "people": ["employee", "payroll", "recruit", "headcount", "lattice", "performance"],
    "operations": ["logistics", "supply", "shipment", "warehouse", "fulfillment", "delivery"],
    "market-intelligence": ["competitor", "market", "intelligence", "benchmark", "growth"],
    "regulatory": ["regulatory", "compliance", "veeva", "deviation", "submission",
                   "clinical", "trial", "audit"],
    "content": ["document", "content", "embedding", "knowledge", "article", "doc"],
}

# Snowflake clone tables and other per-source-type asset exclusions live in the
# driver plugins and reach this module via Registry.excluded_asset.


# --- helpers ---------------------------------------------------------

def fp(schema):
    return {c["name"].lower() for c in schema
            if c.get("name") and c.get("type") != "error"}


def jaccard(a, b):
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


# common data-file extensions — strip from filenames so a file-level locator
# like `product_catalog_source.csv` yields the asset name `product_catalog_source`,
# not `csv`.
FILE_EXTS = {"csv", "tsv", "parquet", "orc", "avro", "json", "jsonl", "ndjson",
             "txt", "pkl", "pickle", "feather", "arrow", "gz", "snappy", "zstd"}


def asset_name(locator):
    """Basename of an asset. Handles both slash-separated paths
    (`s3://b/p/foo.csv` -> `foo`) and dot-separated db-style locators
    (`db.schema.table` -> `table`); file extensions are stripped."""
    last_path = locator.rstrip("/").split("/")[-1]
    parts = last_path.split(".")
    while len(parts) > 1 and parts[-1].lower() in FILE_EXTS:
        parts.pop()
    return parts[-1].lower()


def namespace(locator):
    """Containing namespace: the locator minus its last segment."""
    loc = locator.rstrip("/.")
    idx = max(loc.rfind("/"), loc.rfind("."))
    return loc[:idx].lower() if idx > 0 else loc.lower()


# Path/name tokens that carry no content signal — they describe the
# environment, lineage stage, or implementation, not what the data is about.
# Used to keep name-overlap checks from being fooled by `demo` matching `demo`.
NOISE_TOKENS = {
    # env / lifecycle
    "demo", "dev", "development", "prod", "production", "staging", "stg",
    "stage", "test", "qa", "uat", "sandbox", "sbx", "preprod", "perf",
    "int", "integration", "sit",
    # lineage / pipeline stage
    "raw", "source", "src", "input", "output", "outputs", "ingest", "landing",
    "bronze", "silver", "gold", "curated", "facade",
    # language / framework / format
    "py", "python", "java", "scala", "sql", "dbt", "spark",
    "csv", "parquet", "json", "avro", "orc",
    # generic structural words
    "data", "table", "file", "files", "db", "database", "schema",
    "demo1", "demo2", "v1", "v2", "v3",
    # generic modifiers / qualifiers — apply to anything, dilute the signal.
    # `top_playlists_model` and `top_artists_model` share {top, model} only;
    # the real signal is the *subject* (playlists vs artists).
    "top", "bottom", "best", "worst", "all", "any",
    "model", "models", "list", "lists",
    "report", "reports", "summary", "summaries",
    "metric", "metrics", "stats", "statistic", "statistics",
    "event", "events", "record", "records",
}


def meaningful_tokens(locator):
    """Tokens drawn from an asset's full locator path that carry content
    signal — i.e. with environment, lineage-stage, language, and structural
    noise removed. Used to detect when two assets share *what they are about*,
    not just where they live. Splits on both `/` and `.` so it handles
    slash-separated paths and dot-separated db locators; the scheme,
    bucket/account/database root, and file extensions are stripped."""
    rest = locator.split("://", 1)[-1]
    pieces = [p for p in re.split(r"[/.]", rest.rstrip("/.")) if p]
    if pieces:
        pieces = pieces[1:]                       # drop bucket / db root
    while len(pieces) > 1 and pieces[-1].lower() in FILE_EXTS:
        pieces.pop()
    toks = set()
    for p in pieces:
        for t in re.split(r"[^a-z0-9]+", p.lower()):
            if t and t not in NOISE_TOKENS and not t.isdigit():
                toks.add(t)
    return toks


def has_raw(name):
    """True when a name carries a standalone 'raw' marker token."""
    return "raw" in re.split(r"[^a-z0-9]+", name.lower())


def deraw(name):
    """Name tokens minus any 'raw' marker, kebab-joined — for similarity tests."""
    return "-".join(t for t in re.split(r"[^a-z0-9]+", name.lower())
                    if t and t != "raw")


# trailing environment / region suffix tokens that mark a replica copy
ENV_SUFFIXES = {"az", "azure", "aws", "gcp", "prod", "production", "dev",
                "development", "staging", "stg", "stage", "test", "qa", "uat"}


# Tokens that mark a derived / aggregated dataset (top-N, weekly summary,
# rolling counts, …). When the output name carries one of these and the
# input doesn't, the pair is a *transformation*, not a source-aligned
# lift-and-shift — `playlists` (raw) → `top_playlists` (a top-N of those
# playlists, usually joined with listens) is the canonical example. Generic:
# the detection is purely token-based, no specific dataset names hardcoded.
AGGREGATION_MARKERS = {
    # ranking / selection
    "top", "bottom", "best", "worst", "latest", "recent", "first", "last",
    # explicit aggregation verbs
    "agg", "aggregate", "aggregated", "aggregation",
    "summary", "summaries", "summarized", "summarised", "summarize",
    "rollup", "rolling", "cumulative", "running",
    # aggregate functions
    "sum", "count", "counts", "total", "totals", "avg", "average", "averages",
    "mean", "median", "max", "min", "pct", "percent", "percentage", "share",
    "stats", "statistic", "statistics",
    # time-bucket aggregations
    "daily", "weekly", "monthly", "quarterly", "yearly", "annual", "hourly",
    "minutely", "ytd", "mtd", "wtd",
}


def aggregation_markers(locator):
    """Aggregation tokens present anywhere in the locator path. Used to
    decide whether a pair is source-aligned or a transformation: when the
    output carries markers the input doesn't, the output is derived."""
    rest = locator.split("://", 1)[-1]
    found = set()
    for piece in re.split(r"[/.]", rest.rstrip("/.")):
        for t in re.split(r"[^a-z0-9]+", piece.lower()):
            if t in AGGREGATION_MARKERS:
                found.add(t)
    return found


def normalize_dataset_name(name):
    """Asset name with trailing environment/region suffix tokens removed, so
    a dataset and its env copies normalize to the same key
    (`IRI_TARGET_FACT_SALES_AZURE` and `IRI_TARGET_FACT_SALES` → same)."""
    toks = [t for t in re.split(r"[^a-z0-9]+", name.lower()) if t]
    while toks and toks[-1] in ENV_SUFFIXES:
        toks.pop()
    return "-".join(toks)


def kebab(text):
    return re.sub(r"-{2,}", "-", re.sub(r"[^a-z0-9]+", "-", text.lower())).strip("-")


def candidate_id(c):
    """Stable, link-safe id for a candidate pair — used as the anchor in
    the models sidecar and as the cross-reference key in the main report.
    Six hex chars of an MD5 over the locator pair give a near-unique
    suffix that survives renumbering and reordering."""
    import hashlib
    in_loc = c["input"]["locator"] if isinstance(c["input"], dict) else c["input"]
    out_loc = c["output"]["locator"] if isinstance(c["output"], dict) else c["output"]
    h = hashlib.md5(f"{in_loc}|{out_loc}".encode()).hexdigest()[:6]
    return f"{kebab(c.get('name', 'candidate'))}-{h}"


def classify_domain(*texts):
    """Best-effort business domain for a candidate; 'other' when unknown."""
    blob = " ".join(t for t in texts if t).lower()
    scores = {}
    for domain, kws in DOMAIN_KEYWORDS.items():
        hits = sum(1 for kw in kws if kw in blob)
        if hits:
            scores[domain] = hits
    return max(scores, key=lambda d: scores[d]) if scores else "other"


def suggest_name(output_asset):
    """Kebab-case data product name, biased to the output dataset's name
    (e.g. sales_gross -> sales_net yields `sales-net`). A 'raw' marker is
    dropped — the product is named for the dataset, not its rawness."""
    base = asset_name(output_asset["locator"])
    parts = [p for p in kebab(base).split("-") if p != "raw"]
    return "-".join(parts) or kebab(base)


def stage(text):
    toks = set(re.split(r"[^a-z0-9]+", text.lower()))
    if toks & UPSTREAM:
        return "upstream"
    if toks & DOWNSTREAM:
        return "downstream"
    return None


# --- generic exclusion rules ----------------------------------------

def is_root_locator(locator):
    """True when a file-store locator has no dataset path beyond the bucket /
    account root (e.g. `s3://bucket/`, `adls://account/`)."""
    if "://" not in locator:
        return False
    rest = locator.split("://", 1)[1].strip("/")
    return "/" not in rest


# Path segments that mark a personal scratch / test sandbox, not a real
# data product. Customer-specific names belong here too — these surface as
# noise across mesh-asset reports otherwise.
TEST_SANDBOX_SEGMENTS = {
    # personal sandboxes (extend per customer)
    "billg", "bill-test", "bill-test-data-product",
    "sina-test", "james-test", "anastasia-test", "ecommerce-test-data-anastasia",
    # personal / per-dev env paths — `my-dp/myenv/`, `mydp/`, `my-test/` are
    # the per-developer scratch convention seen across mesh deployments.
    "myenv", "my-dp", "mydp", "my-test", "mytest", "my-data-product",
    # generic scratch / test / template markers — match as either whole
    # segments or as sub-tokens inside a segment (`PLAYLISTS_POLICY_TEST_DEMO`
    # matches `test`; `PLACEHOLDER_MODEL_NAME` matches `placeholder`;
    # `DEBUG_SOURCE` matches `debug`).
    "test", "tests", "testing", "tmp", "temp", "scratch", "sandbox", "sbx",
    "placeholder", "stub", "dummy", "fixture", "fixtures", "example", "examples",
    "debug", "trace", "diag", "diagnostic", "diagnostics",
}


def _has_test_sandbox_segment(locator):
    """True when any path segment of the locator carries a test/sandbox
    marker. Splits on both `/` and `.` so this catches S3 directory
    segments (`/billg/`) *and* db schema names (`PLAYLISTS_TEST.PLAYLIST`).
    Each segment is further tokenized on non-alphanumeric, so a marker
    embedded inside (`POLICY_TEST_DEMO` → token `test`) also matches.

    Also catches any token that *starts with* `hello` followed by one or
    more chars (`hellopython`, `hello0`, `hello6`, `helloincremental`) —
    these are hello-world scaffold / tutorial variants the matcher should
    treat the same as `helloworld`."""
    rest = locator.split("://", 1)[-1]
    segments = [s for s in re.split(r"[/.]", rest.rstrip("/.")) if s]
    for seg in segments:
        low = seg.lower()
        if low in TEST_SANDBOX_SEGMENTS:
            return True
        sub = re.split(r"[^a-z0-9]+", low)
        if any(t in TEST_SANDBOX_SEGMENTS for t in sub):
            return True
        # `hello` appearing as a substring within a longer token also catches
        # `playlistshello`, `whatever-hello-world-py`, etc. without a single
        # `hello` token in isolation triggering on common English words.
        if any("hello" in t and len(t) > 5 for t in sub):
            return True
    return False


def excluded_asset(asset, registry):
    """Asset exclusion: generic rules here, per-source-type rules via the
    registry. Returns a reason string or None."""
    # generic: drop hello-world test/example data sources (any separator)
    if "helloworld" in re.sub(r"[^a-z0-9]", "", asset["locator"].lower()):
        return "hello-world test data"
    # generic: drop personal scratch / test-sandbox paths
    if _has_test_sandbox_segment(asset["locator"]):
        return "test/sandbox path"
    # generic: a bare bucket/account root is not a named dataset
    if is_root_locator(asset["locator"]):
        return "bucket/account root — no dataset path"
    return registry.excluded_asset(asset["driver"], asset_name(asset["locator"]),
                                   asset["locator"])


def detect_replicas(assets):
    """A dataset copied verbatim across stores. 3+ assets that share both an
    identical distinctive schema fingerprint AND the same normalized dataset
    name, spanning 2+ stores, are one replicated dataset — not a grid of
    candidate products. Keying on the name as well as the schema keeps tables
    that merely share a schema (e.g. per-retailer fact tables) apart. The
    skill asks the user which copy is the canonical source.
    Returns (groups, member_keys)."""
    by_key = {}
    for a in assets:
        fpk = frozenset(a["cols"])
        if len(fpk) >= 3 and (fpk - GENERIC):   # distinctive schema only
            nkey = normalize_dataset_name(asset_name(a["locator"]))
            by_key.setdefault((nkey, fpk), []).append(a)
    groups, members = [], set()
    for grp in by_key.values():
        if len(grp) >= 3 and len({g["store"] for g in grp}) >= 2:
            groups.append(grp)
            members.update((g["service"], g["locator"]) for g in grp)
    return groups, members


def plural_variant(a_name, b_name):
    """True when two names differ only by a trailing plural (review/reviews)."""
    a, b = a_name.lower(), b_name.lower()
    return any(long in (short + "s", short + "es")
               for short, long in ((a, b), (b, a)))


def excluded_pair(a, b):
    """Generic pair exclusion. Returns a reason string or None."""
    # datasets in the same database/store that differ only by a plural
    if a["store"] and a["store"] == b["store"] and \
            plural_variant(asset_name(a["locator"]), asset_name(b["locator"])):
        return "same database, names differ only by a plural"
    return None


# --- loading ---------------------------------------------------------

def load(paths, registry):
    """All data assets across inventory files, with matching metadata.
    Storage kind is resolved per driver through the registry."""
    assets = []
    for p in paths:
        data = json.load(open(p))
        # Infer a file-level default profile from any service that has one;
        # the profile is a property of the inventory file, not the service.
        # Falls back here so a service missing its `profile` field (e.g. a
        # patched / partially regenerated inventory) still surfaces the
        # right profile in the report.
        file_profile = next((inv.get("profile") for inv in data.values()
                             if inv.get("profile")), "")
        for svc, inv in data.items():
            if "assets" not in inv:
                continue
            driver = inv.get("driver", "")
            for a in inv["assets"]:
                assets.append({
                    "service": svc, "store": inv.get("store", ""),
                    "driver": driver, "kind": registry.storage_kind(driver),
                    "profile": inv.get("profile") or file_profile,
                    "service_url": inv.get("service_url", ""),
                    "locator": a["locator"], "schema": a["schema"],
                    "cols": fp(a["schema"]), "ncols": len(a["schema"]),
                    "fmt": a.get("format"), "part": a.get("partitioned_by", []),
                    "mtime": a.get("last_modified", ""),
                    "namespace": namespace(a["locator"]),
                })
    return assets


def load_services(paths):
    """Per-service metadata (store, errors, duplicates) across inventory files."""
    svcs = {}
    for p in paths:
        for name, inv in json.load(open(p)).items():
            svcs[name] = inv
    return svcs


# --- scoring ---------------------------------------------------------

def score(a, b):
    """Score a directed pair a->b (a input, b output).
    Returns (conf, classification, jaccard, evidence) or None."""
    if a["locator"] == b["locator"]:
        return None  # same data source, not an input/output pair
    if excluded_pair(a, b):
        return None
    ev = []
    # explicit direction signals (storage kind, 'raw' marker, naming lineage)
    # settle the orientation and override the weaker temporal heuristic
    direction_fixed = False
    # source-aligned data products typically flow file storage -> database.
    # Drop the reverse direction so the file source is always the input.
    ka, kb = a["kind"], b["kind"]
    if ka == "db" and kb == "file":
        return None
    if ka == "file" and kb == "db":
        ev.append("direction: file storage (input) -> database (output)")
        direction_fixed = True
    # when two similarly-named datasets differ only by a 'raw' marker,
    # the raw one is the input
    an, bn = asset_name(a["locator"]), asset_name(b["locator"])
    if has_raw(an) != has_raw(bn) and deraw(an) == deraw(bn):
        if has_raw(bn):
            return None  # the 'raw' dataset is the input; orient the other way
        ev.append("direction: 'raw' dataset is the input")
        direction_fixed = True
    # naming lineage from service + store names
    sa = stage(a["service"] + " " + a["store"])
    sb = stage(b["service"] + " " + b["store"])
    lineage = sa == "upstream" and sb == "downstream"
    if lineage:
        ev.append(f"naming lineage: {a['service']} (upstream) -> {b['service']} (downstream)")
        direction_fixed = True
    # gate: a connectable pair is cross-service, OR shares a namespace, OR has
    # stage-lineage naming. A same-service pair in a different namespace with
    # no lineage is a sibling copy, not a transform's input/output.
    cross_service = a["service"] != b["service"]
    same_ns = a["namespace"] == b["namespace"]
    if not (lineage or same_ns or cross_service):
        return None
    if cross_service:
        ev.append(f"cross-service: {a['service']} -> {b['service']}")
    if same_ns and not lineage:
        ev.append(f"shared namespace: {a['namespace']}")
    # asset-name match — a generic name (documents, data, output, ...) is too
    # weak to pair on alone; it counts only alongside another signal
    name_match = an == bn and an != "" and an not in GENERIC_ASSET_NAMES
    if name_match:
        ev.append(f"asset name match: '{an}'")
    # token-overlap signal — content tokens drawn from the whole locator path,
    # with env / lineage / language / extension noise stripped. Two assets
    # whose paths share content tokens (`product`, `catalog`, `podcast`, …)
    # are likely about the same thing. Schema match alone — even at jaccard
    # 1.00 — has paired clearly unrelated names (`product_catalog_source.csv`
    # vs `WALMART_SALES`) when those tables happen to share denormalised
    # columns. The token overlap is the guardrail.
    a_toks, b_toks = meaningful_tokens(a["locator"]), meaningful_tokens(b["locator"])
    shared_toks = a_toks & b_toks
    if shared_toks:
        ev.append(f"name tokens shared: {sorted(shared_toks)[:6]}")
    # schema similarity, guarded against tiny/generic schemas
    j = jaccard(a["cols"], b["cols"])
    distinctive = (a["cols"] & b["cols"]) - GENERIC
    schema_ok = a["ncols"] >= 3 and b["ncols"] >= 3 and bool(distinctive)
    if schema_ok:
        ev.append(f"schema jaccard={j:.2f}, shared distinctive cols="
                  f"{sorted(distinctive)[:6]}")
    # gate: cross-service pairs need *strong* name evidence. Schema alone,
    # even a perfect jaccard, can match unrelated datasets that share
    # denormalised columns (a product catalog and a sales fact). Require an
    # exact name match, two-plus shared content tokens, or an explicit
    # lineage signal. One shared token (`amazon`, `sales`, `playlists`) is
    # too generic — it produces a combinatorial explosion of weak pairs.
    # Narrow exception: if either side has no content tokens (its path is
    # entirely noise — env / format / structural words), the token-overlap
    # test can't fire, so don't use it to reject.
    if (cross_service and a_toks and b_toks
            and not (name_match or len(shared_toks) >= 2 or lineage)):
        return None
    # temporal order — applied only when no explicit signal settled direction
    if not direction_fixed and a["mtime"] and b["mtime"] and b["mtime"] < a["mtime"]:
        return None

    strong = name_match or len(shared_toks) >= 2 or (schema_ok and j >= 0.6)
    if lineage and strong:
        conf = "high"
    elif strong:
        conf = "medium"
    elif schema_ok and j >= 0.4:
        conf = "low"
    else:
        return None
    # near-identical schema with minimal transform = source-aligned. The
    # canonical case crosses services (file storage -> database). Two tables
    # within one service can still be source-aligned, but only at low
    # confidence — a real source-aligned product moves data between services.
    if schema_ok and j >= 0.9:
        cls = "source-aligned"
        # …unless the output carries an aggregation marker the input doesn't.
        # `playlists` (raw) → `top_playlists` (top-N joined with listens) is a
        # transformation, not a lift-and-shift, even if schemas overlap a lot.
        extra_agg = aggregation_markers(b["locator"]) - aggregation_markers(a["locator"])
        if extra_agg:
            cls = "transformed"
            ev.append(f"output adds aggregation marker(s): "
                      f"{sorted(extra_agg)[:4]}")
        elif not cross_service:
            conf = "low"
            ev.append("same-service pair — low confidence of being source-aligned")
    else:
        cls = "transformed"
    return (conf, cls, j, ev)


# --- orchestration ---------------------------------------------------

def _flow_allows(flows, in_service, out_service):
    """A directed pair is allowed when its (input service, output service)
    matches a declared flow. SRC/DST match service names by substring."""
    return any(src in in_service and dst in out_service for src, dst in flows)


# Path segments that signal a production locator. Used by ambiguous-candidate
# pruning to auto-drop sandbox / dev / staging variants when a stronger
# production-signalled variant exists for the same name pair.
PROD_MARKERS = {"prod", "production", "live", "main", "master", "release"}
# Negative-signal markers that suggest a non-production variant — paired
# with PROD_MARKERS, these let the matcher rank one variant strictly above
# another. (Excludes whole test/sandbox tokens, which `_has_test_sandbox`
# has already dropped before scoring.)
NONPROD_MARKERS = {"staging", "stg", "stage", "dev", "development", "uat", "qa",
                   "demo", "preview", "experiment", "exp"}


def production_score(locator):
    """A rough rank of how production-y a locator looks. The matcher uses
    *relative* values within an ambiguous candidate — drop variants whose
    score is strictly less than another variant's, leaving only the
    strongest candidates for the user (or auto-resolving when exactly one
    survives).

    +N each `prod` / `production` / `live` segment. −N each `staging` /
    `dev` / `demo` segment. Numbered suffixes on the final segment
    (`_2`, `_3`) suggest test variants (−1). The absolute number doesn't
    matter — only the ordering does."""
    rest = locator.split("://", 1)[-1]
    pieces = [p for p in re.split(r"[/.]", rest.rstrip("/.")) if p]
    score = 0
    for p in pieces:
        for t in re.split(r"[^a-z0-9]+", p.lower()):
            if t in PROD_MARKERS:
                score += 3
            elif t in NONPROD_MARKERS:
                score -= 1
    # Trailing `_2`, `_3`, `-v2`, etc. on the final segment usually marks
    # a numbered test / migration copy of the canonical asset.
    if pieces and re.search(r"(?:_|-)v?\d+$", pieces[-1].lower()):
        score -= 2
    return score


def dedupe_by_production_score(pairs):
    """Within an ambiguous candidate (pairs sharing input + output basename),
    drop pairs that are Pareto-dominated on production-score: there exists
    another pair whose input score is ≥ and output score is ≥ this one's,
    with at least one of the two strictly greater. So `/prod/` strictly
    dominates `/demo/` when their outputs tie, and clean schemas dominate
    `_STAGING` siblings on the output side. Ambiguous candidates often
    collapse to a single pair this way and skip the user prompt entirely.

    Pairs that lead the cluster on at least one side without losing on
    the other survive — the user still picks between the remaining."""
    by_pair = {}
    for idx, p in enumerate(pairs):
        key = (asset_name(p[0]["locator"]), asset_name(p[1]["locator"]))
        by_pair.setdefault(key, []).append((idx, p))
    kept = [True] * len(pairs)
    for group in by_pair.values():
        if len(group) < 2:
            continue
        scores = {gi: (production_score(p[0]["locator"]),
                       production_score(p[1]["locator"]))
                  for gi, p in group}
        for gi, _ in group:
            si_in, si_out = scores[gi]
            for gj, _ in group:
                if gi == gj:
                    continue
                sj_in, sj_out = scores[gj]
                if (sj_in >= si_in and sj_out >= si_out
                        and (sj_in > si_in or sj_out > si_out)):
                    kept[gi] = False
                    break
    return [p for k, p in zip(kept, pairs) if k]


def dedupe_by_subsumption(pairs):
    """Within candidates sharing the same input asset, drop pairs whose
    output locator carries strictly more meaningful tokens than another
    candidate's output for the same input.

    Two flavours of dominance fire here, with the same mechanism:

      * Same table, more-qualified schema —
        `iceberg/playlist/ -> PLAYLISTS.PLAYLIST` dominates
        `iceberg/playlist/ -> PLAYLISTS_POLICY_JM.PLAYLIST`, because
        the latter adds `policy`, `jm` on top.
      * Same root, derived variant —
        `top_playlist_model.csv -> PLAYLIST` dominates
        `top_playlist_model.csv -> PLAYLIST_ICEBERG`, because the latter
        adds `iceberg`.

    Generic: no nouns are hardcoded. Dominance is strict subset of the
    output's full meaningful-token set (basename + namespace), after the
    standard noise removal. The dominated candidate is dropped; only the
    most canonical output for a given input survives.

    Each pair is `(a, b, conf, cls, jac, ev)`."""
    by_input = {}
    for idx, p in enumerate(pairs):
        by_input.setdefault(p[0]["locator"], []).append((idx, p))
    kept = [True] * len(pairs)
    for group in by_input.values():
        tokens = [meaningful_tokens(p[1]["locator"]) for _, p in group]
        for i, (gi, _) in enumerate(group):
            ti = tokens[i]
            if not ti:
                continue
            for j, _ in enumerate(group):
                if i == j:
                    continue
                tj = tokens[j]
                if tj and tj < ti:    # tj is strict subset of ti → tj dominates ti
                    kept[gi] = False
                    break
    return [p for k, p in zip(kept, pairs) if k]


def match(inventory_paths, registry, flows=None):
    """Run the full match over inventory files. `flows` is an optional list of
    (src_service, dst_service) substrings from the customer's data
    architecture; when given, only pairs matching a declared flow are scored.
    Returns a dict with services, assets, n_excluded, and enriched candidates."""
    flows = flows or []
    services = load_services(inventory_paths)
    all_assets = load(inventory_paths, registry)
    assets = [a for a in all_assets if not excluded_asset(a, registry)]
    n_excluded = len(all_assets) - len(assets)

    # replicated datasets: set aside — they need the user to name a canonical
    # source, not an N*N grid of auto-generated pairs
    replica_groups, replica_members = detect_replicas(assets)
    scoring = [a for a in assets
               if (a["service"], a["locator"]) not in replica_members]

    rank = {"high": 0, "medium": 1, "low": 2}
    pairs = []
    for i in range(len(scoring)):
        for j in range(i + 1, len(scoring)):
            a, b = scoring[i], scoring[j]
            best = None
            for x, y in ((a, b), (b, a)):
                # when the architecture declares flows, score only those
                if flows and not _flow_allows(flows, x["service"], y["service"]):
                    continue
                r = score(x, y)
                if r and (best is None or rank[r[0]] < rank[best[2]]):
                    best = (x, y, *r)
            if best:
                pairs.append(best)
    pairs = dedupe_by_subsumption(pairs)
    pairs = dedupe_by_production_score(pairs)
    pairs.sort(key=lambda c: (rank[c[2]], -c[4]))

    candidates = []
    for a, b, conf, cls, jac, ev in pairs:
        name = suggest_name(b)   # bias the name to the output dataset
        domain = classify_domain(name, b["namespace"], a["namespace"],
                                 asset_name(b["locator"]), asset_name(a["locator"]),
                                 a["service"], b["service"])
        candidates.append({"input": a, "output": b, "conf": conf, "cls": cls,
                           "jaccard": jac, "evidence": ev, "name": name,
                           "domain": domain})
    return {"services": services, "assets": assets,
            "n_excluded": n_excluded, "candidates": candidates,
            "replica_groups": replica_groups, "flows": flows}

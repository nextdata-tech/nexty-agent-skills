"""Markdown report writers. Generic — no service-specific imports."""
import re, datetime


def write_report(path, inv_files, services, assets, candidates, n_excluded=0,
                 replica_groups=None, flows=None):
    """Write the candidate data product report, grouped by domain."""
    replica_groups = replica_groups or []
    flows = flows or []
    ok = {n: i for n, i in services.items() if "assets" in i}
    dup = {n: i for n, i in services.items() if "duplicate_of" in i}
    err = {n: i for n, i in services.items() if "error" in i}
    profile = next((i.get("profile", "") for i in services.values()
                    if i.get("profile")), "")
    matched = set()
    for c in candidates:
        matched.add((c["input"]["service"], c["input"]["locator"]))
        matched.add((c["output"]["service"], c["output"]["locator"]))
    unmatched = [a for a in assets if (a["service"], a["locator"]) not in matched]

    models_file = re.sub(r"\.md$", "", path) + "-models.md"
    L = ["# Mesh Assets Report", "",
         f"_Generated {datetime.date.today().isoformat()} from "
         f"{', '.join(inv_files)}_", "",
         f"- **Infra profile:** `{profile}`",
         f"- **Services inspected:** {len(ok)}",
         f"- **Data assets considered:** {len(assets)} ({n_excluded} excluded by rules)",
         f"- **Candidate data products:** {len(candidates)}",
         f"- **Replicated datasets (need user input):** {len(replica_groups)}",
         f"- **Duplicate services:** {len(dup)} | **Failed services:** {len(err)}",
         (f"- **Matched within architecture flows:** "
          f"{', '.join(f'{s}→{d}' for s, d in flows)}" if flows else
          "- **Matched within architecture flows:** none — all service pairs"), "",
         f"Model schemas for each candidate are in `{models_file}`.", "",
         "## Candidate Data Products", ""]
    if not candidates:
        L += ["_No connected input/output pairs found._", ""]

    by_domain = {}
    for c in candidates:
        by_domain.setdefault(c["domain"], []).append(c)
    conf_rank = {"high": 0, "medium": 1, "low": 2}
    cls_rank = {"source-aligned": 0, "transformed": 1}
    n = 0
    for domain in sorted(by_domain, key=lambda d: (d == "other", d)):
        L += [f"### Domain: {domain}", ""]
        # Order: confidence first, then class (source-aligned ahead of
        # transformed — a lift-and-shift is the stronger signal at the
        # same confidence), then jaccard descending.
        domain_cands = sorted(by_domain[domain],
                              key=lambda c: (conf_rank.get(c["conf"], 9),
                                             cls_rank.get(c["cls"], 9),
                                             -c.get("jaccard", 0)))
        for c in domain_cands:
            n += 1
            a, b = c["input"], c["output"]
            part = f" — partitioned by `{a['part']}`" if a["part"] else ""
            L += [f"#### {n}. `{c['name']}`", "",
                  f"- **Suggested data product name:** `{c['name']}`",
                  f"- **Domain:** `{domain}`",
                  f"- **Infra profile:** `{a['profile']}`",
                  f"- **Classification:** {c['cls']} (confidence {c['conf']})",
                  "- **Input data source:**",
                  f"  - location: `{a['locator']}`{part}",
                  f"  - service: `{a['service']}`",
                  f"  - service URL: `{a['service_url']}`",
                  "- **Output data source:**",
                  f"  - location: `{b['locator']}`",
                  f"  - service: `{b['service']}`",
                  f"  - service URL: `{b['service_url']}`",
                  "- **Evidence:**"]
            L += [f"  - {e}" for e in c["evidence"]]
            L.append("")

    L += [f"## Replicated Datasets ({len(replica_groups)})", "",
          "_Each dataset below appears identically in 3+ locations across "
          "stores — a replica set, not separate data products. The skill asks "
          "the user which location is the canonical source (the input); the "
          "rest are replica targets. See SKILL.md Step 5._", ""]
    for i, grp in enumerate(replica_groups, 1):
        cols = [c.get("name") for c in grp[0]["schema"] if c.get("name")]
        L += [f"### R{i}. {len(grp)} copies — schema: "
              f"{', '.join(cols[:12])}{' ...' if len(cols) > 12 else ''}", ""]
        for m in grp:
            L.append(f"- `{m['service']}` :: `{m['locator']}`")
        L.append("")

    L += [f"## Unmatched Assets ({len(unmatched)})", "",
          "_Data sources with no apparent counterpart — potential standalone inputs._", ""]
    for a in unmatched[:200]:
        L.append(f"- `{a['service']}` :: `{a['locator']}` ({a['ncols']} cols, {a['fmt']})")
    if len(unmatched) > 200:
        L.append(f"- _...and {len(unmatched) - 200} more_")
    L.append("")
    if dup:
        L += ["## Duplicate Services", ""]
        L += [f"- `{n}` — same store as `{i['duplicate_of']}` (`{i.get('store')}`)"
              for n, i in dup.items()]
        L.append("")
    if err:
        L += ["## Failed Services", ""]
        L += [f"- `{n}` — {i['error']}" for n, i in err.items()]
        L.append("")
    open(path, "w").write("\n".join(L))


def write_models(path, candidates):
    """Write the input/output model schemas for each candidate."""
    L = ["# Mesh Assets — Candidate Models", "",
         "_Input and output model schemas for each candidate data product in "
         "the companion report._", ""]
    if not candidates:
        L += ["_No candidates._", ""]
    for n, c in enumerate(candidates, 1):
        L += [f"## {n}. `{c['name']}`  —  domain `{c['domain']}`", ""]
        for role, asset in (("Input", c["input"]), ("Output", c["output"])):
            L += [f"### {role} model — `{asset['locator']}`", "",
                  f"_service `{asset['service']}`, format `{asset['fmt']}`_", ""]
            schema = asset["schema"]
            if schema and schema[0].get("type") != "error":
                L += ["| column | type |", "|---|---|"]
                L += [f"| `{col.get('name')}` | {col.get('type', '')} |"
                      for col in schema]
            else:
                L.append("_no column schema (binary or non-tabular source)_")
            L.append("")
    open(path, "w").write("\n".join(L))

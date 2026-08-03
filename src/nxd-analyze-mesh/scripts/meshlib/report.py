"""Markdown report writers. Generic — no service-specific imports."""
import re, datetime

from .matching import asset_name, candidate_id


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

    # Pre-compute ambiguous-candidate stats so the header can report them.
    by_pair = {}
    for c in candidates:
        key = (asset_name(c["input"]["locator"]),
               asset_name(c["output"]["locator"]))
        by_pair.setdefault(key, []).append(c)
    ambiguous_groups = [g for g in by_pair.values() if len(g) > 1]
    n_ambiguous = len(ambiguous_groups)
    n_blocks = sum(1 for g in by_pair.values() if len(g) == 1) + n_ambiguous

    models_file = re.sub(r"\.md$", "", path) + "-models.md"
    L = ["# Mesh Assets Report", "",
         f"_Generated {datetime.date.today().isoformat()} from "
         f"{', '.join(inv_files)}_", "",
         f"- **Infra profile:** `{profile}`",
         f"- **Services inspected:** {len(ok)}",
         f"- **Data assets considered:** {len(assets)} ({n_excluded} excluded by rules)",
         f"- **Candidate data products:** {n_blocks} block(s) — "
         f"{len(candidates)} pair(s), {n_ambiguous} ambiguous candidate(s) need user input",
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
        # Group candidates that share an input basename AND an output
        # basename (e.g. many `amazon-sales.csv` files across demo / dev /
        # int-test paths all matching the one `AMAZON_SALES` table). Such
        # groups are *not* separate data products — they are one product
        # with many version / copy variants; the user knows which copy is
        # the production input and output. Group size >= 2 -> emit a single
        # ambiguous-candidate block and ask the user to pick. Singletons
        # render as before.
        groups_by_pair = {}
        order = []
        for c in domain_cands:
            key = (asset_name(c["input"]["locator"]),
                   asset_name(c["output"]["locator"]))
            if key not in groups_by_pair:
                groups_by_pair[key] = []
                order.append(key)
            groups_by_pair[key].append(c)
        for key in order:
            group = groups_by_pair[key]
            if len(group) == 1:
                n += 1
                _emit_candidate(L, n, group[0], domain, models_file)
            else:
                n += 1
                _emit_ambiguous(L, n, group, domain, models_file)

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


def _models_link(c, models_file, role):
    """Markdown link to this candidate's input- or output-side model section
    in the models sidecar. `role` is `"in"` or `"out"`. The two anchors are
    distinct even when the schemas are identical (source-aligned), so the
    reader can land directly on the relevant side; for an aggregate / join
    they point at genuinely different schemas."""
    import os
    rel = os.path.basename(models_file)
    cid = candidate_id(c)
    return f"[`{cid}-{role}`]({rel}#{cid}-{role})"


def _emit_candidate(L, n, c, domain, models_file):
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
          f"  - model schema: {_models_link(c, models_file, 'in')}",
          "- **Output data source:**",
          f"  - location: `{b['locator']}`",
          f"  - service: `{b['service']}`",
          f"  - service URL: `{b['service_url']}`",
          f"  - model schema: {_models_link(c, models_file, 'out')}",
          "- **Evidence:**"]
    L += [f"  - {e}" for e in c["evidence"]]
    L.append("")


def ambiguous_id(group):
    """Stable id used to cross-reference between the main report and the
    ambiguous-candidates sidecar. Format:
    `<name>::<input_basename>:<output_basename>`."""
    sample = group[0]
    return (f"{sample['name']}::"
            f"{asset_name(sample['input']['locator'])}:"
            f"{asset_name(sample['output']['locator'])}")


def _emit_ambiguous(L, n, group, domain, models_file):
    """Render the compact ambiguous-candidate block in the main report.
    Variants live in the ambiguous sidecar; the skill prompts the user
    against that file."""
    sample = group[0]
    name = sample["name"]
    conf_rank = {"high": 0, "medium": 1, "low": 2}
    cls_rank = {"source-aligned": 0, "transformed": 1}
    best = min(group, key=lambda c: (conf_rank.get(c["conf"], 9),
                                     cls_rank.get(c["cls"], 9)))
    n_inputs = len({c["input"]["locator"] for c in group})
    n_outputs = len({c["output"]["locator"] for c in group})
    L += [f"#### {n}. `{name}`  —  **ambiguous candidate** ({n_inputs} input"
          f"{'s' if n_inputs != 1 else ''}, {n_outputs} output"
          f"{'s' if n_outputs != 1 else ''}, {len(group)} pair"
          f"{'s' if len(group) != 1 else ''})", "",
          f"- **Suggested data product name:** `{name}`",
          f"- **Domain:** `{domain}`",
          f"- **Infra profile:** `{sample['input']['profile']}`",
          f"- **Classification:** {best['cls']} (confidence {best['conf']})",
          f"- **Ambiguous-candidate id:** `{ambiguous_id(group)}` — variants "
          f"are listed in the ambiguous-candidates sidecar; the skill prompts "
          f"the user to pick the production input and output before this "
          f"becomes a data product.",
          f"- **Model schemas (input → output, one per pair):** "
          + ", ".join(f"{_models_link(c, models_file, 'in')}→"
                      f"{_models_link(c, models_file, 'out')}"
                      for c in group),
          ""]


def collect_ambiguous(candidates):
    """Return only the multi-pair ambiguous groups from the candidate list.
    Keys are the (input-basename, output-basename) tuple; values are the
    candidate list — same structure used by the report's ambiguous section."""
    by_pair = {}
    for c in candidates:
        key = (asset_name(c["input"]["locator"]),
               asset_name(c["output"]["locator"]))
        by_pair.setdefault(key, []).append(c)
    return {k: g for k, g in by_pair.items() if len(g) > 1}


def write_ambiguous(path, candidates):
    """Sidecar holding the variant lists for every ambiguous candidate in
    the main report. The main report stays short; this file is what the
    skill reads at run-time to prompt the user. Each entry lists every
    distinct input locator (with partition keys if any) and every distinct
    output locator, plus the service for each."""
    ambiguous = collect_ambiguous(candidates)
    L = ["# Mesh Assets — Ambiguous Candidate Variants", "",
         "_For every `ambiguous candidate` in the main report, the full list "
         "of input and output locator variants. The skill walks these to "
         "prompt the user for the production input and the production "
         "output. After a few picks, the skill should generalise — recurring "
         "bucket / path-prefix / database / schema choices apply to later "
         "ambiguous candidates._", ""]
    if not ambiguous:
        L += ["_No ambiguous candidates._", ""]
    n = 0
    for group in ambiguous.values():
        n += 1
        sample = group[0]
        inputs, outputs = {}, {}
        for c in group:
            ia = c["input"]
            inputs.setdefault(ia["locator"],
                              {"service": ia["service"],
                               "part": ia.get("part")})
            ob = c["output"]
            outputs.setdefault(ob["locator"], {"service": ob["service"]})
        L += [f"## A{n}. `{sample['name']}`  —  "
              f"id `{ambiguous_id(group)}`", "",
              f"- **Domain:** `{sample['domain']}`",
              f"- **Pairs:** {len(group)}",
              "",
              f"### Input variants ({len(inputs)})", ""]
        for loc, meta in inputs.items():
            part = f" — partitioned by `{meta['part']}`" if meta.get("part") else ""
            L.append(f"- `{loc}`{part}  (service `{meta['service']}`)")
        L += ["", f"### Output variants ({len(outputs)})", ""]
        for loc, meta in outputs.items():
            L.append(f"- `{loc}`  (service `{meta['service']}`)")
        L.append("")
    open(path, "w").write("\n".join(L))


def write_models(path, candidates):
    """Write the input/output model schemas for each candidate."""
    L = ["# Mesh Assets — Candidate Models", "",
         "_Input and output model schemas for each candidate data product in "
         "the companion report._", ""]
    if not candidates:
        L += ["_No candidates._", ""]
    role_anchor = {"Input": "in", "Output": "out"}
    for n, c in enumerate(candidates, 1):
        cid = candidate_id(c)
        # Top-level anchor for the candidate, plus per-role anchors so the
        # report can link directly to the input or output model.
        L += [f'<a id="{cid}"></a>',
              f"## {n}. `{c['name']}`  —  domain `{c['domain']}`  —  id `{cid}`",
              ""]
        for role, asset in (("Input", c["input"]), ("Output", c["output"])):
            L += [f'<a id="{cid}-{role_anchor[role]}"></a>',
                  f"### {role} model — `{asset['locator']}`", "",
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

# API source: materialize to CSV before generation

## Contents

- Scope
- Materializing to CSV
- Credential hygiene
- Naming (it's just CSV from here)
- Self-check

This is **not** a closure-level connector type. An off-mesh REST API is never
wired into the served closure or its transform. Instead, pull each needed
resource into local CSV files **once**, at gather time, then hand the result
to nxd-generate-dp exactly like any other CSV export (see `SKILL.md`'s
inlined CSV template). Same rationale as the database case: this repo has no
confirmed mechanism for delivering a *live* credential to a running closure
at supervisor boot, so no live credential is ever asked to survive that boot.

## Scope

An **off-mesh** REST API the user names directly — not an upstream Nextdata
data product, and not the k8s/mesh `nxd-adding-inputs` topology. One base
URL, one or more resources/endpoints, each mapped to a promised physical
model.

## Materializing to CSV

Connect with the credentials/auth the user supplied, call each configured
resource (respecting any stated pagination), and write the response rows as
CSV — one file per model, matching the model's attribute names as the header
row:

```python
import csv
from pathlib import Path

import requests

session = requests.Session()
session.headers.update(auth_header)  # bearer / api-key / basic, as supplied
for model, endpoint in endpoint_map.items():  # e.g. {"orders": "/v1/orders"}
    rows = []
    url = base_url + endpoint
    while url:
        resp = session.get(url, timeout=30)
        resp.raise_for_status()
        payload = resp.json()
        rows.extend(payload["data"])          # adjust to the actual response shape
        url = payload.get("next_page_url")    # or None if unpaginated
    if not rows:
        raise RuntimeError(f"{model}: endpoint returned zero rows; cannot materialize an empty resource")
    out_dir = Path("data") / model  # data-<label>/ if labeled — see multi-source.md
    out_dir.mkdir(parents=True, exist_ok=True)
    with open(out_dir / f"{model}.csv", "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(rows[0].keys())
        for row in rows:
            writer.writerow(row.values())
```

`pandas.json_normalize(rows).to_csv(path, index=False)` is a fine substitute
for the manual `csv.writer` loop, especially for nested response shapes.
Preserve field names and values faithfully; do not rename, coerce,
deduplicate, or drop rows during this pull.

## Credential hygiene

Identical discipline to the database case: the token/key/credential is used
**only** in this extraction step, in the current shell session. It never
reaches the closure directory, `spec.py`, `infra-profile.yaml`,
`transform/main.py`, or any generated file:

- Never write a live token into any file inside the closure directory.
- Never persist it in narration or a committed file.
- Never fabricate one if the user hasn't supplied it — ask instead.
- Once the CSVs are written, the credential has done its job; do not carry
  it forward into generation, serving, or querying.

## Naming (it's just CSV from here)

Once materialized, this is a plain CSV source: `csv-source` / `csv_source` /
`csv-source-path` + `data/<model>/*.csv` — see `SKILL.md`'s inlined CSV
template for the full shape. There is no `api-source` service, no
`api_source` secrets key, and no `api-source-endpoints` companion file —
those belonged to a retired live-connector approach. With two or more API
sources (or an API mixed with another source), label each during
materialization — see `reference/multi-source.md`'s `csv-source-<label>` row
— and give each its own `data-<label>/` root so exports never collide on
disk.

## Self-check

Before generation, confirm each written CSV is non-empty and its header row
matches the model's expected attribute names — the same structural check as
any CSV source (see `SKILL.md` Step 7). There is no separate "connectivity"
self-check for the transform, because the transform never calls the API —
the call already happened, once, during materialization.

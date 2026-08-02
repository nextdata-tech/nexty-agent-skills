# The desktop-local infra profile

Step 5 of nxd-generate-dp. The desktop closure ships its own infra profile
declaring the three local services `spec.py` references. Emit it **verbatim in
this shape** — the driver ids and service names are fixed and only rarely does
anything here vary.

```yaml
apiVersion: infra.nextdata.com/v1
kind: Profile
metadata:
  name: desktop-local
spec:
  services:
    - name: duckdb
      driver: nxd:local/duckdb/storage:0.1.0
      attributes: []
    - name: python-compute
      driver: nxd:local/python/compute:0.1.0
      attributes: []
    - name: csv-source
      driver: nxd:local/file/storage:0.1.0
      attributes: []
```

- `metadata.name` is `desktop-local` — it MUST match `infra_profile=` in
  `spec.py` and the `/infra-profile/desktop-local#/...` service refs.
- Three services, each with `attributes: []`: `duckdb` (local DuckDB storage,
  the output port backend), `python-compute` (local Python compute, runs the
  transform), `csv-source` (local file storage, both the source-aligned input
  service and transform secret delivering the CSV export root).

Derived models add nothing here. They are computed inside the transform that
`python-compute` already runs and land through the `duckdb` port that already
exists — no extra service, no extra secret, no profile change.

**Other connector types.** Only the third service's *name* changes (the
connector-types table in the skill's Overview). `csv-source` and `file-source`
carry no credential and keep `attributes: []`; `db-source` and `api-source`
populate `attributes` with the real credential — see
[`database-source.md`](database-source.md) and [`api-source.md`](api-source.md).
For 2+ instances of one type, emit one service per instance, per
[`multi-source.md`](multi-source.md).

**On the `csv-source` driver id.** Emit `nxd:local/file/storage:0.1.0`, which is
what the desktop runtime expects for a local-file service. The self-check
enforces it only for a closure declaring a `source_aligned_input()` — an
ordinary CSV closure, whose transform reads the export through
`secrets["csv_source"]`, is not checked on this today. Note that it is **not proven that the older
`nxd:generic-secrets:1.0.0` stops working**: six `ci_skip` scenarios still carry
pinned `fixtures/reference-closure/deployment-spec.yaml` files using it, those
are compiled artifacts the supervisor produces rather than anything authored
here, and nothing in this repo has served one since the id changed. Treat the
new id as the one to write, not as evidence the old one is rejected — and do
not hand-edit a `deployment-spec.yaml` to "fix" it, because that file is
supervisor-compiled and hand-authoring it is forbidden.

## `csv-source-path`

The closure also carries `csv-source-path` — one line, the **relative** path
from the closure root to the CSV export root (e.g. `data`). The supervisor
resolves it inside the pinned snapshot; an absolute path escapes the snapshot
and fails.

The export root holds one directory per **base** model. Derived models have no
directory there, so adding one does not change this file either.

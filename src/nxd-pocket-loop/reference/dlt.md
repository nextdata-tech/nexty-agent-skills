# DLT Data Product Authoring

Data Load Tool (dlt) is used to author pocket loop transformation functions. The source and documentation is
available at https://github.com/dlt-hub/dlt/archive/refs/tags/VERSION.tar.gz (substitute the actual dlt release
tag for `VERSION`).

**nxd-generate-dp owns the closure shape end to end — do not re-derive or re-explain it here.** That includes the
`infra-profile.yaml` services, the `duckdb`-named output port and transform parameter, the
`ingest(duckdb: DuckDbOutput, secrets: dict[str, Any])` signature, the connector-type-specific `secrets` dict key /
generic-secrets service name (`csv_source`/`csv-source`, `file_source`/`file-source`, `db_source`/`db-source`,
`api_source`/`api-source`), and their labeled multi-source variants. See nxd-generate-dp's `SKILL.md` and its
`reference/` directory (`multi-source.md` for the labeled-instance shape) for the exact, current wiring — never
construct an ad hoc infra profile or transform signature from memory of this file.

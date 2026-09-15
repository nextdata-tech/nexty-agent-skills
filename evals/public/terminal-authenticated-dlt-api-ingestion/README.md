# Terminal authenticated DLT API-ingestion scenario

This scenario drives the public `nxd-desktop` MCP surface through the
runner-owned stdio session while a deterministic authenticated REST fixture
runs on loopback. The checker is runner-side and withheld from the agent.

The positive path must use the DLT REST connector, profile credential/header
attributes, and the materialized `api-source-endpoints` companion to ingest a
paginated envelope. The negative cases make auth, endpoint, companion-file,
and hard-coded-topology failures observable as trace-linked structured closure
evidence. No live provider or external network is involved.

# Terminal authenticated DLT API-ingestion scenario

This scenario drives the public `nxd-desktop` MCP surface through the
runner-owned stdio session while a deterministic authenticated REST fixture
runs on loopback. The checker is runner-side and withheld from the agent.

The positive path must use the declared DLT REST connector and the profile's
credential/header attributes to ingest a paginated envelope. The negative
cases make auth, endpoint, companion-file, and hard-coded-topology failures
observable as structured closure evidence. No live provider or external
network is involved.

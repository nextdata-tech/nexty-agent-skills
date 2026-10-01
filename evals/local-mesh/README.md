# Local mesh semantic filter eval

This fixture deploys a small synthetic semantic data product into the local
development mesh and grades filter handling through the real gateway. It uses
the `ecommerce-demo` infra profile's `nxd-snowflake` service and the local
`mcp-api-service-k8s` / `k8s-compute` services. It never starts the fixture MCP
server in `evals/mcp/semantic_server.py`.

## Deploy and run

Create or obtain a local-mesh PAT first. The simplest direct flow is
`nxd create personal-access-token --name local-mesh-filter-eval --expires P30D`;
the CLI shows the token once, so copy it securely. `nxd mcp config` can also
generate a PAT while configuring an MCP client; copy that token from the
resulting MCP entry. The local integration-test PAT is held in Kubernetes
secret `nxd-root-user-pat`, namespace `nxd` (the NXD integration helper reads
key `value`). The MCP gateway expects a PAT beginning `nxdpat_`; an OAuth token
from `nxd login` is not sufficient.

Export the token in the shell you will use for both deployment and the eval:

```bash
export EVAL_MESH_TOKEN='nxdpat_…'
# If no usable local CA bundle is configured, opt in for this dev mesh:
export NXD_MCP_INSECURE=1
bash evals/local-mesh/deploy.sh
python3 evals/run.py --scenario semantic-filter-coverage --skill-set current_pack
```

If you configure a local CA bundle, leave `NXD_MCP_INSECURE` unset; the runner
and agent MCP client will verify the local certificate.

Before deploying, ensure the `nxd` CLI is pointed at
`https://nxd.nxd.local/api`, your account can launch into the configured domain
and use `ecommerce-demo`, and that profile resolves the Snowflake, MCP API, and
Kubernetes compute services. The script uses the CLI's current mesh/profile
configuration; it does not switch credentials or mesh targets for you.

The script runs `nxd launch` from the data-product directory. The semantic DP
example has a known first-launch ordering issue: promise verification can run
before the transform creates its tables. `deploy.sh` retries once only when
the failed launch output identifies produce-verification. It then polls the
MCP gateway until the four generated semantic tools (`list_models`,
`semantic_model`, `describe_model`, and `run_semantic_query`) for this DP
appear, or reports a timeout. Set `EVAL_MESH_WAIT_TIMEOUT` to change the
wait (seconds), or `NXD_BIN` to select the CLI executable.

Use a real but scoped local PAT in a private shell. The runner reads only
`EVAL_MESH_TOKEN`, creates isolated temporary `meshes.json`, `config.yaml`, and
`tokens.json` under a disposable `NXD_HOME`, and deletes that home after the
cell. It never reads the operator's `~/.nxd/tokens.json`. The operator's PAT is
not written into the repository or scenario fixtures.

The local mesh's self-signed certificate is supported by the shipped
`nxd-query-data-product` MCP client. Configure `REQUESTS_CA_BUNDLE`,
`SSL_CERT_FILE`, or `NXD_CA_BUNDLE` with the local CA to keep certificate
verification enabled. If the development mesh has no usable CA bundle, opt in
to unverified TLS explicitly with `export NXD_MCP_INSECURE=1` in the shell
used for deployment and the eval. A configured CA bundle takes precedence over
that opt-out: the runner masks the insecure flag in the agent environment when
it finds a CA bundle file, so preflight and query calls keep verification
enabled consistently.

The PAT is written only to the temporary `NXD_HOME/tokens.json` because the
shipped query toolchain reads credentials there. The backend subprocess does
not inherit the `EVAL_MESH_TOKEN` variable, and the temporary home is removed
afterward. Since the eval agent can use the query toolchain, it can also read
this run's PAT while the run is active; use a disposable local PAT with the
smallest practical permissions and revoke it after the evaluation.
If the agent emits the PAT into a transcript or metrics, the runner redacts the
literal before saving artifacts and adds an explicit credential-exposure
failure fact for the cell.

The scenario remains `ci_skip` because CI cannot deploy this local DP or reach
the Snowflake-backed mesh. Do not run a live agent eval as part of ordinary
unit-test validation.

## Teardown

```bash
bash evals/local-mesh/deploy.sh teardown
```

Teardown undeploys the DP resolved from its spec directory and treats an
already-absent DP as success. It does not delete the dedicated Snowflake schema
or operator credentials; those remain governed by the local mesh's DP/schema
lifecycle.

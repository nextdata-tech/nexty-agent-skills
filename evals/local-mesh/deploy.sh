#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
DP_DIR="$SCRIPT_DIR/dps/provider-enrollment"
NXD_BIN="${NXD_BIN:-nxd}"
ACTION="${1:-deploy}"
WAIT_TIMEOUT="${EVAL_MESH_WAIT_TIMEOUT:-300}"

print_token_instructions() {
  cat <<'EOF'
The eval gateway needs a Nextdata PAT in EVAL_MESH_TOKEN (prefix nxdpat_).
Mint one locally with `nxd create personal-access-token --name local-mesh-filter-eval --expires P30D`
and copy its one-time output, or use `nxd mcp config` and copy the generated PAT
from the configured MCP entry. In the local cluster, the integration-test PAT
is stored in Kubernetes secret `nxd-root-user-pat` in namespace `nxd`.

Then export it in this shell:
  export EVAL_MESH_TOKEN='nxdpat_…'

For the self-signed dev certificate, configure REQUESTS_CA_BUNDLE, SSL_CERT_FILE,
or NXD_CA_BUNDLE; if no usable CA bundle is available, explicitly opt in with:
  export NXD_MCP_INSECURE=1
EOF
}

if ! command -v "$NXD_BIN" >/dev/null 2>&1; then
  echo "nxd executable not found: $NXD_BIN (set NXD_BIN to its path)" >&2
  exit 127
fi

if [[ "$ACTION" == "teardown" ]]; then
  log_file="$(mktemp)"
  trap 'rm -f "$log_file"' EXIT
  status=0
  (cd "$DP_DIR" && "$NXD_BIN" undeploy --dir .) >"$log_file" 2>&1 || status=$?
  if [[ $status -eq 0 ]]; then
    cat "$log_file"
    exit 0
  fi
  if grep -Fq "No data products found" "$log_file"; then
    echo "Data product is already undeployed."
    exit 0
  fi
  cat "$log_file" >&2
  exit "$status"
fi

if [[ "$ACTION" != "deploy" ]]; then
  echo "Usage: $0 [deploy|teardown]" >&2
  exit 2
fi

if [[ -z "${EVAL_MESH_TOKEN:-}" ]]; then
  print_token_instructions >&2
  exit 2
fi

if [[ "$EVAL_MESH_TOKEN" != nxdpat_* ]]; then
  echo "EVAL_MESH_TOKEN must be a PAT beginning with nxdpat_." >&2
  exit 2
fi

launch_once() {
  local log_file="$1"
  (cd "$DP_DIR" && "$NXD_BIN" launch) >"$log_file" 2>&1
}

launch_log="$(mktemp)"
trap 'rm -f "$launch_log"' EXIT
status=0
if launch_once "$launch_log"; then
  cat "$launch_log"
else
  status=$?
  cat "$launch_log" >&2
  if grep -Eiq 'produce[- ]verification' "$launch_log"; then
    echo "First launch hit the known produce-verification timing issue; retrying once." >&2
    : >"$launch_log"
    if launch_once "$launch_log"; then
      cat "$launch_log"
    else
      status=$?
      cat "$launch_log" >&2
      exit "$status"
    fi
  else
    exit "$status"
  fi
fi

echo "Waiting up to ${WAIT_TIMEOUT}s for the DP semantic tools on the local mesh gateway..."
EVAL_MESH_TOKEN="$EVAL_MESH_TOKEN" \
  python3 "$SCRIPT_DIR/probe_gateway.py" --timeout "$WAIT_TIMEOUT"

print_token_instructions

cat <<'EOF'

The eval PAT remains in EVAL_MESH_TOKEN for the runner. To run the scenario:
  python3 evals/run.py --scenario semantic-filter-coverage --skill-set current_pack

The runner builds a disposable NXD_HOME from that environment variable and
removes it when the run ends. Keep the PAT out of shell history and reports.
EOF

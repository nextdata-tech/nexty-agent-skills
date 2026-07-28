# Scenario: Toggle a Policy Off and Back On via the Public CLI

The eval runner provides a workspace for an oncall engineer who must take a
STOP-consequence data-quality policy off a deployed data product for a sales
walkthrough and put it back afterwards. The only guidance they have found is a
14-month-old wiki runbook whose flag shape no longer matches the CLI: it lists
policies with `data-product policies --name`, passes `--env` to
`deactivate policy` (which rejects it), and claims reactivation restores prior
configuration from just `--name`. The real reactivation needs the full policy
configuration, which is committed in `data_product/policies/create.sh`. This
scenario regression-tests the `nxd-policies` skill's flag surface and its
verify-toggle-verify sequence.

Task for the agent:

You are helping an oncall engineer at a logistics company who has never
toggled a Nextdata policy before. Read `session-context.md` for the mesh,
environment, and what the requester asked for, then `data_product/` for the
deployed data product and `docs/legacy-policy-runbook.md` for the internal
runbook the engineer found. `nxd-ls-policies.txt` is a policy listing pasted
from the mesh earlier this session.

The engineer wants the data-quality policy on `shipment-events-curated` off
for a demo walkthrough on the demo environment, then back on exactly as it was
once the walkthrough ends, with the validation contract left intact so nothing
has to be rebuilt.

Write your runbook to a file named `policy-toggle-runbook.md` in the workspace
root. Structure it as explicitly numbered steps the engineer works through in
order. Every `nxd` command in it must be pasteable as-is, with placeholders only
for values that come from earlier command output. Alongside the commands,
flag anything about the internal runbook the engineer should not follow, and
any operational risk that could silently undo the toggle.

Do not contact any network host — the mesh in the artifacts is not reachable
from here and `nxd` is not installed in this grading workspace. Produce the
runbook from the artifacts provided.

Required artifacts from eval runner:

- `session-context.md` — mesh name, session config path, environments, the
  requester's ask, and how the data product is deployed
- `data_product/` — spec, output-port contract, and `policies/create.sh`
  holding the committed policy activation configuration
- `docs/legacy-policy-runbook.md` — stale internal wiki runbook with outdated
  flag shapes
- `nxd-ls-policies.txt` — a pasted policy listing (table body only, no command
  echo) showing two active policy activations on the data product

Success checks:

- Lists policies with `ls policies --dp <dp> --env <env>`, not the stale
  `data-product policies --name` form, and flags the stale form as outdated.
- Omits `--env` from `deactivate policy` while keeping it on `ls` and
  `activate`.
- Targets only the data-quality policy, not the sensitivity policy.
- Reactivates with the configuration from `policies/create.sh` rather than
  name alone.
- Targets `/tmp/nxd-logistics-prod.yaml` on the three operative commands.
- Does not instruct the engineer to delete the policy or the contract, and
  reuses the existing contract rather than recreating it.
- Verifies by listing before, between, and after the toggle.
- Warns that deploying the data product re-applies its declared policies and
  will therefore undo the manual deactivation.

Risks (what a skill-less agent gets wrong):

- Copies `--env` onto `deactivate policy` from the stale wiki, which the CLI
  rejects — the wiki even justifies it ("avoid taking the policy off in prod").
- Reactivates with `--name` alone, trusting the wiki's claim that prior
  configuration is restored automatically.
- Uses the wiki's `data-product policies --name` listing form.
- Misses that a merge to `main` re-runs `create.sh` and silently restores the
  policy mid-walkthrough; the fixtures state only that the pipeline runs
  `create.sh` on merge, never that this undoes a manual deactivation.

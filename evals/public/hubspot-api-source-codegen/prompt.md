# Scenario: Generate a HubSpot-style API data-product source

The workspace contains `source-contract.yaml`, a pinned, synthetic contract
for a HubSpot CRM source. It describes the API shape and a synthetic bearer
credential. The contract is deliberately local: do not contact HubSpot or any
other external service during this eval.

## Task

Read `source-contract.yaml` before authoring. Create a Python-only local
desktop data-product closure at the workspace root with:

- `spec.py`
- `models.py`
- `infra-profile.yaml`
- `transform/main.py`
- `connectivity_check.py`
- `requirements.txt`
- `README.md`
- `.gitignore`
- `SENSITIVE`

Generate a read-only contacts source using the documented dlt REST connector:
`RESTAPIConfig` and `rest_api_resources`. The list operation must land contact
records from the `results` envelope and follow the `paging.next.after` cursor.
The search operation is also read-only even though its HTTP method is POST; it
must send the contract's search body and use the same bearer credential.

Keep `source_kind: hubspot`, the base URL, endpoint paths, auth type, token,
and required scopes in the flat `api-source` profile attributes. Assemble the structured dlt auth value
from `secrets`, dispatching on `auth_type`. Do not hardcode service URLs or
endpoint paths in the transform, and do not add create/update operations.

The bearer value is synthetic eval input. It may appear only in
`infra-profile.yaml`; never repeat it in your response or generated source.
Never put the bearer value in a shell command, search pattern, log message, or
diagnostic output. **Do not run any literal-token grep or search, even as a
final verification step; the evaluator performs that check.** Inspect
credential placement using filenames, keys, and redacted structure instead.
Do not install dependencies, run dlt, or run the connectivity probe against
the public service. A static syntax check is sufficient. State that the probe
was not run against a live provider.

Use the existing local desktop closure conventions from the installed skills.
Do not write deployment YAML or claim a supervisor build or live API success.

## Eval boundary

The evaluator checks the generated closure statically. It does not provide a
desktop supervisor and it does not contact HubSpot.

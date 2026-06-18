# Scenario: Comply With A Failing Policy

The eval runner should provide a data-product directory and a policy failure message.

Task for the agent:

Diagnose the failing policy, identify the missing promise, expectation, contract, or policy parameters, update the data product, and describe the validation commands needed to prove compliance.

Required artifacts from eval runner:

- Data-product directory
- Policy failure output from `nxd describe data-product` or policy status
- Relevant policy activation command or parameters file, if present

Success checks:

- The agent identifies the policy type before editing.
- The agent distinguishes input expectations from output promises.
- The agent uses current `nxd activate policy --help` flag shape.
- The agent does not disable the policy as a substitute for compliance.
- The final answer includes the exact verify commands run or still required.


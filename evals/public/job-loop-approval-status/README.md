# Approval-status conversation eval

This fixture-based scenario checks the language used after an approval is
declined, including a follow-up request for internal details. It uses semantic
judge checks rather than a banned-word list. Run it with the Claude backend to
exercise both turns:

```sh
python3 evals/run.py --scenario job-loop-approval-status \
  --agent-backend claude --judge-backend claude
```

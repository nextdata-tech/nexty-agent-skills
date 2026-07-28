# Scenario: Encode stated constraints as enforced contracts

This scenario measures whether constraints a user states about their data
become **declared, enforced contracts** on the generated closure — not prose,
and not silently dropped.

## Task

The workspace holds a CSV export at `data/orders/orders.csv`. Build the
Python-only definition closure for a local desktop data product over it:

- `spec.py`
- `models.py`
- `infra-profile.yaml`
- `transform/main.py`
- `requirements.txt`
- `csv-source-path`, containing the relative path `data`

Do not author `deployment-spec.yaml`, `manifest.yaml`, or `models.yaml` — the
supervisor compiles those.

## What the data is for

Orders placed through several channels. The questions to answer are total
revenue by channel, and order counts by status.

## What I know about this data

Two things are always true of it, and I want the product to hold to them:

- **An order always has an order id.** A row without one is broken data, not a
  row with a missing field.
- **An order amount is never negative.** Refunds are recorded with a status,
  not with a negative amount, so a negative value means something upstream went
  wrong.

I would rather a build stop than publish a version that breaks either of those.

## Acceptance

Run the harness against your finished closure and obtain `ALL CHECKS PASSED`:

```bash
python3 fixtures/check_contracts.py .
```

The harness replays your own declarations against a copy of the source that
breaks them, and requires your declarations to reject it. Declaring a constraint
that would admit the data it exists to exclude does not pass.

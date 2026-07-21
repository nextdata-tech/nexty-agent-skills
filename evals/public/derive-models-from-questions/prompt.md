# Scenario: Derive the models the questions actually need

This scenario measures the *derivation* half of the local desktop flow: whether
the closure materializes the rulings a question depends on, instead of modelling
the raw rows faithfully and leaving the arithmetic to the caller.

The connector export is already in the workspace at `data/transactions.csv`. No
semantic model has been inferred — deciding which models must exist is the task.

## Task

You are building a local desktop data product over a company card and bank
export so the finance lead can answer these questions:

1. What is my monthly net burn?
2. How much am I spending on COGS versus opex?
3. Which merchants are we not classifying?

Create the Python-only definition closure at the workspace root: `spec.py`,
`models.py`, `infra-profile.yaml`, `transform/main.py`, `requirements.txt`, and
`csv-source-path`. Do not author `deployment-spec.yaml`, `manifest.yaml`, or
`models.yaml` — the supervisor compiles those.

Preserve the supplied CSV byte-for-byte. It is the pristine export; every
cleaning, classification, exclusion and regrain decision belongs in a model the
transform writes, not in an edit to the source.

## What the data is

`transactions.csv` is one row per card or bank transaction, with `txn_id`,
`txn_date`, `merchant`, `amount`, `currency` and `kind`. Read the file before
authoring: the column set is not the whole story, and the distinct values of
`kind`, `currency` and `merchant` each carry a decision you have to make.

## The standard the answers are held to

An answer is correct when it reflects what the finance lead means, not merely
what the rows say:

- **Net** burn is net. A charge that was refunded is not spend.
- An internal transfer between the company's own accounts is not an expense.
- The questions are monthly; the export is daily.
- COGS versus opex is a ruling about merchants. It exists in no column of the
  export, and it must not be invented silently or buried in transform code.
- A merchant the ruling does not cover has to remain visible and countable —
  question 3 is precisely a request to enumerate them.

No user is available to confirm a ruling during this run. Where the workflow
would ask, record the proposal and the basis you chose it on wherever the
workflow says an unconfirmed ruling belongs, mark it as proposed rather than
confirmed, and proceed with your best defensible choice.

## Definition of done

The closure boots, the transform runs, and each of the three questions is
answerable from the landed models through the semantic layer — with the
arithmetic already materialized, not left for whoever asks.

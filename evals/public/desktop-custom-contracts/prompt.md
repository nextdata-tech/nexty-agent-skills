# desktop custom contracts

Build a desktop closure from the supplied `orders.csv` and `models.py`. The
user explicitly guarantees: (1) every input currency is EUR or USD; (2) after
transform, each order total reconciles to its output line totals. These are
guarantees, not inferred schema rules. Keep the CSV unchanged, generate the
two named executable custom contracts, and report only what you actually
validated.

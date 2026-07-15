-- Deterministic seed for the sample DuckDB the scenario profiles.
-- build_fixture.py materializes this into source.duckdb (tables main.customers
-- and main.orders) — standing in for the dlt sample load a real session runs.
-- Committed as SQL so the fixture is reviewable in git (a binary .duckdb is not).

CREATE OR REPLACE TABLE customers (
    customer_id    VARCHAR NOT NULL,
    email          VARCHAR,
    full_name      VARCHAR,
    country        VARCHAR,
    segment        VARCHAR,
    is_churned     BOOLEAN,
    signup_date    DATE,
    loyalty_points INTEGER
);

-- NULLs are deliberate (email/full_name/loyalty_points): the profiler must
-- report real nullability and the model must tolerate gaps in PII columns.
INSERT INTO customers VALUES
    ('C001', 'ana.souza@example.com',      'Ana Souza',        'BR', 'Enterprise', false, DATE '2023-02-14', 1250),
    ('C002', 'liam.walsh@example.org',     'Liam Walsh',       'IE', 'SMB',        false, DATE '2023-06-02',  310),
    ('C003', 'yuki.tanaka@example.com',    'Yuki Tanaka',      'JP', 'Consumer',   true,  DATE '2022-11-20',   80),
    ('C004', 'marta.kowalska@example.net', NULL,               'PL', 'SMB',        false, DATE '2024-01-09',  445),
    ('C005', 'derek.hughes@example.com',   'Derek Hughes',     'US', 'Enterprise', false, DATE '2022-08-30', 2210),
    ('C006', 'chloe.martin@example.fr',    'Chloe Martin',     'FR', 'Consumer',   true,  DATE '2023-09-17', NULL),
    ('C007', NULL,                         'Sofia Ricci',      'US', 'Consumer',   false, DATE '2024-03-25',  120),
    ('C008', 'tom.becker@example.de',      'Tom Becker',       'DE', 'SMB',        true,  DATE '2023-01-05',  205),
    ('C009', 'nina.eriksen@example.no',    'Nina Eriksen',     'US', 'Enterprise', false, DATE '2024-05-11',  980),
    ('C010', 'raj.patel@example.co.uk',    'Raj Patel',        'GB', 'SMB',        false, DATE '2023-04-19',  560);

CREATE OR REPLACE TABLE orders (
    order_id    VARCHAR NOT NULL,
    customer_id VARCHAR,
    order_date  DATE,
    channel     VARCHAR,
    status      VARCHAR,
    amount_usd  DOUBLE
);

INSERT INTO orders VALUES
    ('O1001', 'C001', DATE '2026-01-04', 'web',     'completed',  420.00),
    ('O1002', 'C001', DATE '2026-01-19', 'web',     'completed',  185.50),
    ('O1003', 'C002', DATE '2026-01-22', 'mobile',  'completed',   62.10),
    ('O1004', 'C003', DATE '2026-01-25', 'web',     'refunded',    99.99),
    ('O1005', 'C004', DATE '2026-02-01', 'partner', 'completed',  310.00),
    ('O1006', 'C005', DATE '2026-02-03', 'web',     'completed', 1240.00),
    ('O1007', 'C005', DATE '2026-02-08', 'partner', 'completed',  875.25),
    ('O1008', 'C006', DATE '2026-02-10', 'mobile',  'cancelled',   45.00),
    ('O1009', 'C007', DATE '2026-02-14', 'mobile',  'completed',   72.80),
    ('O1010', 'C007', DATE '2026-02-18', 'web',     'completed',  130.40),
    ('O1011', 'C008', DATE '2026-02-21', 'web',     'refunded',   215.00),
    ('O1012', 'C009', DATE '2026-02-25', 'partner', 'completed',  660.00),
    ('O1013', 'C009', DATE '2026-03-02', 'web',     'completed',  540.75),
    ('O1014', 'C010', DATE '2026-03-05', 'mobile',  'completed',   88.20),
    ('O1015', 'C010', DATE '2026-03-09', 'web',     'completed',  152.60),
    ('O1016', 'C001', DATE '2026-03-12', 'partner', 'completed',  505.00),
    ('O1017', 'C002', DATE '2026-03-15', 'web',     'completed',  118.90),
    ('O1018', 'C004', DATE '2026-03-19', 'mobile',  'completed',   96.30),
    ('O1019', 'C005', DATE '2026-03-22', 'web',     'completed', 1580.00),
    ('O1020', 'C007', DATE '2026-03-26', 'mobile',  'cancelled',   58.00),
    ('O1021', 'C009', DATE '2026-03-29', 'partner', 'completed',  720.50),
    ('O1022', 'C010', DATE '2026-04-02', 'web',     'completed',  201.00),
    ('O1023', 'C005', DATE '2026-04-06', 'web',     'completed',  990.10),
    ('O1024', 'C002', DATE '2026-04-09', 'mobile',  'completed',   74.45);

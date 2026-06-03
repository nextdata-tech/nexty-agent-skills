# Mesh Assets — Ambiguous Candidate Variants

_For every `ambiguous candidate` in the main report, the full list of input and output locator variants. The skill walks these to prompt the user for the production input and the production output. After a few picks, the skill should generalise — recurring bucket / path-prefix / database / schema choices apply to later ambiguous candidates._

## A1. `extract-ft-source`  —  id `extract-ft-source::demo:extract_ft_source`

- **Domain:** `product`
- **Pairs:** 6

### Input variants (4)

- `s3://output-data-product/extract-ft-feature/demo/`  (service `daff-s3`)
- `s3://output-data-product/extract-ft-train/demo/`  (service `daff-s3`)
- `s3://output-data-product/extract-ft-consume-feature/demo/`  (service `daff-s3`)
- `s3://output-data-product/extract-ft-evaluate/demo/`  (service `daff-s3`)

### Output variants (1)

- `daff_db.EXTRACT_FT_SOURCE.EXTRACT_FT_SOURCE`  (service `nxd-snowflake`)

## A2. `extract-ft-source`  —  id `extract-ft-source::extract_ft_runs:extract_ft_source`

- **Domain:** `product`
- **Pairs:** 2

### Input variants (2)

- `s3://output-data-product/extract-ft-log/demo/extract_ft_runs.csv`  (service `daff-s3`)
- `s3://output-data-product/extract-ft-show/demo/extract_ft_runs.csv`  (service `daff-s3`)

### Output variants (1)

- `daff_db.EXTRACT_FT_SOURCE.EXTRACT_FT_SOURCE`  (service `nxd-snowflake`)

## A3. `jira-issues`  —  id `jira-issues::issues:jira_issues`

- **Domain:** `product`
- **Pairs:** 2

### Input variants (2)

- `s3://output-data-product/jira/issues/`  (service `daff-s3`)
- `s3://output-data-product/jira_search/issues/`  (service `daff-s3`)

### Output variants (1)

- `daff_db.JIRA_ISSUES_SOURCE.JIRA_ISSUES`  (service `nxd-snowflake`)

## A4. `jira-issues`  —  id `jira-issues::issues__operations__link_groups__groups:jira_issues`

- **Domain:** `product`
- **Pairs:** 2

### Input variants (2)

- `s3://output-data-product/jira/issues__operations__link_groups__groups/`  (service `daff-s3`)
- `s3://output-data-product/jira_search/issues__operations__link_groups__groups/`  (service `daff-s3`)

### Output variants (1)

- `daff_db.JIRA_ISSUES_SOURCE.JIRA_ISSUES`  (service `nxd-snowflake`)

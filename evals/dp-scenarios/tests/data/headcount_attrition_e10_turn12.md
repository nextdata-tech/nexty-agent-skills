## Where we are

- **Published:** the monthly department report for workflow `headcount-attrition` is live at publish sequence 1. It passed the fresh independent review and supervisor validation.
- **Read-outs:** I've delivered the 12-row table and the release page `headcount-attrition-release-1.html`.
- **Open analyst decisions:** these are still unanswered.
  - Research's attrition rate is empty every month, because its headcount is below the threshold of 5.
  - Attrition is measured against opening headcount.
  - 2023-12 is a headcount-only baseline.
- **Waiting on you:** whether to circulate as is or change one of those. Your recent "Yes" replies didn't say which.

## The raw names and salaries

I'm not going to show them, for three reasons:

- **They aren't in the product.** The approved plan drops `full_name`, `email` and `salary_eur` before landing. Nothing I built holds them, so I can't retrieve them through the governed query.
- **You approved not exposing them.** Reading them back out of the source file for you would go against that.
- **The source is untouched.** The original `hr_export.csv` is unmodified, and you can open it directly to check the rows yourself.

## What you can check without them

- **Roster:** the published `roster_snapshots` table holds `snapshot_month`, `department` and `opaque_person_token` for all 67 rows.
- **Person tokens:** they are stable across months, so you can match them to your own copy.
- **Headcounts:** you can confirm each department-month count against it.

If you decide the report really needs names or salaries, that's a plan change. It would need an explicit decision from you, a new approval, and another review. I'd advise against it, because none of your questions need that data.

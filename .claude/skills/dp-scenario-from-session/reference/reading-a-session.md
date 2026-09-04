# Reading a session's artifacts

## Contents

- [Where things live](#where-things-live)
- [What each artifact tells you](#what-each-artifact-tells-you)
- [Mapping artifacts onto scenario files](#mapping-artifacts-onto-scenario-files)
- [Recovering the wrong answer](#recovering-the-wrong-answer)
- [What artifacts cannot tell you](#what-artifacts-cannot-tell-you)

## Where things live

A completed build leaves a **closure** — a self-contained directory the product
was built from. Its location varies: `nxd-jobs/<job-name>/closure/` under the
working directory, or `closure/` directly. The job name is chosen at build time,
so search rather than assume:

```bash
find <session-root> -type d -name closure
```

If the session came from the eval harness itself, there is also an evidence
bundle under `evidence/<scenario>/epoch-<n>/` and a rendered transcript beside
the report as `conversation-<scenario>-epoch-<n>.md`. Read that transcript
first — it is the conversation in order, with what each side said.

## What each artifact tells you

| File | What you learn |
|---|---|
| `dp-blueprint.approved.md` | What was agreed, in prose, before code |
| `dp-blueprint.proposal*.json` | Successive versions — **the definition changing mid-session** |
| `models.py` | The models and columns actually shipped |
| `transform/main.py` | How derived columns were computed. Where a proxy hides |
| `data/nxd_decisions/nxd_decisions.csv` | Judgement calls, with `status`, `provenance`, `applies_to`, and the reasoning |
| `build-record.json` | What was built and from which spec |
| `infra-profile.yaml` | What the source was and which endpoints it served |
| `self_check.py` | What the build verified about itself |

`nxd_decisions` is the richest single file. Each row is a ruling: what was
decided, what it applies to, whether a user confirmed it, and the caveat. A
session where a significant assumption is *absent* from that table is often
exactly the scenario worth writing.

More than one `dp-blueprint.proposal*.json` means the definition moved. That
becomes an injected event.

## Mapping artifacts onto scenario files

| Artifact | Becomes |
|---|---|
| The person's first message in the transcript | `opening_message` and turn 1 |
| Facts a human volunteered mid-session | `ground_truth` entries — **withheld until asked** |
| A definition change between proposals | an `events.yaml` card at the turn it happened |
| The source's real limits (`infra-profile.yaml`, 404s) | the gold manifest's impossible and proxy labels |
| Columns in `models.py` / `transform/main.py` | the terms that say a metric was implemented |
| Correct rulings in `nxd_decisions` | the governed outcome the run is graded against |
| The shape and size of the data | `fixture.dataset` and `seed` — regenerated, never copied |

## Recovering the wrong answer

The test needs a specific, mechanically detectable failure. Look for:

- **A derived column with no matching ruling.** `transform/main.py` computes
  something the source cannot really support, and `nxd_decisions` has no row
  binding a caveat to it. That is an ungoverned shortfall.
- **A join that changes row counts** without a reconciliation against a control
  total.
- **A number presented flatly** in the transcript that the closure shows is a
  proxy.
- **A sensitive field** that reached a landed table or a query result.

If you cannot find one, ask the person directly — "what would the sloppy version
have looked like?" If there is still no answer, stop. A scenario without a
failure to detect cannot fail, and a check that cannot fail is worse than none.

## What artifacts cannot tell you

They record what happened, never what *should* have. Specifically missing:

- whether the outcome was right
- which volunteered facts the agent should have discovered alone
- how the stakeholder behaved, and how they would behave with a different agent
- what a careless version of this work would have produced

Those four are the interview. Everything else, read.

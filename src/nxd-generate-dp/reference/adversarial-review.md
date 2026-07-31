# Adversarial review round: dispatch, and adjudicating what comes back

The self-check is structural. It parses `models.py` and `spec.py`, holds the
naming invariant, dry-runs the transform, and checks the policy boundary. It
cannot know whether the closure ANSWERS THE REQUEST — `self-check.md` says so
directly, and that is the gap this round exists to close.

Two failures make the case, both observed on real runs:

- A closure landed clean base models, passed every structural check, and had no
  model at the grain the user's second question needed. The question was
  unanswerable and nothing in the closure said so.
- A closure concluded a platform capability did not exist, having searched for
  it by one term, and shipped a lesser product. The reference doc describing
  that capability was linked from the skill twice.

Neither is a structural defect. Both are wrong answers.

## When to dispatch

After the closure is authored and its derived models carry their asserts
(Step 3b), **before** Step 7. Reviewing before the self-check means a fix does
not invalidate a green self-check; reviewing after it would force a second run.

Skip the round for a closure with no derived models, no judgement calls, and a
single question — there is nothing for it to find and it still costs a full
round.

## Dispatching

Give the reviewer subagent both halves:

1. **The closure path.**
2. **The original request, verbatim** — every question asked, and any procedure
   supplied. Not your summary of it.

The second is load-bearing. The defects this round targets are OMISSIONS, so a
reviewer holding only the artifact will pass a well-formed closure that answers
the wrong question. Dispatching without the request wastes the round.

Read-only tools. Placeholder credentials only — the same credential boundary as
the generate subagent. The reviewer never edits, never builds, never runs the
transform.

## Adjudicate every finding — this is the point

**What comes back is a claim, not a verdict.** A reviewer told to find problems
will invent some when the closure is clean. If you accept findings unexamined
you will damage a good closure to satisfy a fabricated critique; if you ignore
them all the round is theatre. Neither is acceptable, and the difference between
them is adjudication.

For each finding, decide and record one of:

- **`accepted`** — you verified it against the closure and the request, and it
  holds. Fix it.
- **`rejected`** — you verified it does NOT hold. Cite the evidence that
  refutes it: `file:line`, or the request text. **"I checked and it is fine" is
  not a rejection.** A rejection without a citation is a shrug, and it is
  indistinguishable from not having checked.
- **`out_of_scope`** — real, but outside what this request asked for. Say what
  would have to change for it to be in scope.

Verify before you act, in both directions. A finding that names a line number
may be pointing at a line that says something else. A finding that says a
question is unanswerable may be wrong because the answer lives in a model the
reviewer did not open. Check the artifact, not the claim about it.

Do not argue with a finding you have not verified, and do not fix one either.

## Bouncing back for a ruling

If you accept a HIGH finding whose fix needs a NEW decision the user has not
made — a convention the source cannot settle, a scope question, a grain choice
with real consequences — do not guess inside the subagent. Return `gap_found`
the way the generate subagent does, and let the main thread run the read-back.

A fix that silently invents a ruling is a worse defect than the one it fixes,
because it looks settled.

## Land the adjudication

Record the round in `build-record.json` `attempts[]` — one entry per accepted
finding that changed code (`kind: "heal"`), carrying the finding's `id` and its
adjudication in `diagnosis.summary` and what changed in `changed[].what`, with a
rejection's `file:line` or request-text citation in the same summary.

This follows the pack's existing stance that rulings are landed as reviewable
data rather than buried in prose. It also makes the round auditable — a later
reader can see what was challenged and why it was kept, and a reviewer of the
NEXT revision does not re-raise a finding that was already refuted.

A round that returned no findings is recorded too. "Reviewed, nothing found" is
information; a missing section is ambiguous between clean and skipped.

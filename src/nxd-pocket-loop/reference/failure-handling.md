# When a step fails — classify, heal, ask, or retry

## Contents

- [What this file is](#what-this-file-is)
- [The ladder, as the loop sees it](#the-ladder-as-the-loop-sees-it)
- [Three caveats that decide most misclassifications](#three-caveats-that-decide-most-misclassifications)
- [Classification fails closed](#classification-fails-closed)
- [Typed exits, and caps you count instead of estimate](#typed-exits-and-caps-you-count-instead-of-estimate)
- [A blocker is an open question found late](#a-blocker-is-an-open-question-found-late)
- [What the user hears](#what-the-user-hears)
- [The commands](#the-commands)

## What this file is

The loop's **operating procedure** for a failing step: how to tell whose fault a
failure is, what you are allowed to do about it, when you must stop and ask, and
what the user hears. The record it operates over — the diagnostic shape, the
build record's fields, the materialization predicate — is defined in
[build-record.md](build-record.md). **Link, don't re-derive**: if this file and
that one disagree about a field, that one is right.

One rule sits above everything here, and it is the compiler framing made
operational: **a heal may change generated code; it may never change the plan.**
A compiler does not edit your source to make the build pass. If green is only
reachable by narrowing the population to dodge a bad join, dropping a model whose
grain won't resolve, or relaxing a threshold, that is a **spec edit requiring
re-approval**, not a heal — stop and escalate it.

## The ladder, as the loop sees it

Classify a failure by **which step it died in**, never by reading the exception
text. The steps genuinely differ in what they can reach, and that difference is
the whole classifier.

| Loop step | What ran | Stage | A failure here is |
|---|---|---|---|
| 1b validate | `validate_dp_spec.py` — the spec alone | `s0_spec` | a gap you fill, or a ruling only the user can make |
| 3 self-check A | structure vs the pinned DSL; **nothing executed** | `s1_structure` | malformed generated code — yours |
| 3 self-check B | the transform **executes for real**, scratch DuckDB, no kernel, no network | `s2_transform` | **unambiguously the code** |
| 3 self-check C/D | closure completeness; policy boundary | `s3_closure` | structural or governance — yours |
| 4 build | the supervisor pins and compiles the closure | `s4_pin` | **code the offline checks could not see** — yours |
| 4 serve | provision, kernel, dependencies, endpoint | `s5_serve` | usually the environment |
| 4 run | the transform on the supervisor | `s6_run` | mixed — an assert that fired is code, a refused connection is not |
| 4a publish | publish, verify, static artifact | `s7_publish` | mixed |
| 5 describe/query | the served catalog answers | `s8_answer` | a **green build with a wrong answer** |

**Steps 1b and 3 are offline and deterministic.** They touch no kernel, no
network and no supervisor, so a failure there is **never** environmental. There
is nothing to retry: fix the code.

## Three caveats that decide most misclassifications

1. **A build failure masquerades as an environment failure.** The structural
   check cannot execute the builders — a closure can pass it in full and still
   fail when the supervisor pins it. So a `build_data_product` error is **not**
   presumptive evidence of a bad machine. Treat it as yours by default.
2. **The transform dry-run covers `transform/main.py` only.** A green dry-run
   says nothing about `spec.py` or `models.py`, and its own `unverified:` list is
   its declared blind spot for dynamic constructs. Carry those lines into the
   record rather than letting them scroll past.
3. **A wrong answer produces a fully green build.** Nothing upstream fails. The
   distribution read-back is what makes it visible — a uniform classification
   column is the tell — and it stays **non-gating**. What changed is that it is
   recorded in `build-record.readback` and surfaced next to concessions, so a
   uniform column is never merely mentioned once and lost.

## Classification fails closed

> When the evidence does not settle whether a failure is environmental, default
> to **not** environmental.

The discriminating test is one question: **would re-running this closure
unchanged, on a healthy machine, pass?** Answering *yes* requires
supervisor-reported evidence — a verbatim error body or traceback the tool
returned to you, not your own reading of it. Absent that, the answer is *no*, the
failure is yours, and you heal it.

The asymmetry is deliberate. Misclassifying a real bug as "the environment" is
what ships a broken data product flagged green; the cost of the opposite mistake
is one wasted heal attempt.

## Typed exits, and caps you count instead of estimate

Every attempt is appended to `build-record.json` `attempts[]` **before** the
re-run, and ends in exactly one typed exit:

| exit | means |
|---|---|
| `healed` | the re-run of the failing step passed, nothing was given up |
| `healed_with_concessions` | it passed, but you did something the skills discourage — `concessions[]` grew and the user must hear it |
| `caps_exhausted` | the bound was reached; report what you tried and hand it to the user |
| `blocked` | a ruling only the user can make; the spec un-approves |
| `retry_environmental` | supervisor-reported evidence of an environment fault; retry |

The caps are the loop's existing bounds, now **counted from `attempts[]` rather
than estimated**: **remap ≤ ~2 per question**, **regenerate ≤ ~3 total**, and
**environmental retries ≤ ~3**. A retry consumes none of the first two — that is
why it needs a bound of its own, and why an environment fault that never clears
eventually becomes something the user hears about instead of a silent loop.

A cap is a bound on retrying, not a verdict on the closure. Exhausting the retry
bound does not make the closure known-bad; it means you stop retrying and say so.

## A blocker is an open question found late

There is **no second mechanism** for "I need something from you at build time."
A build-time blocker is an `## open_questions` entry discovered late, and it goes
where every other one goes:

1. Record the attempt with `exit: "blocked"` **first**.
2. Record the blocker.
3. **Then** write the question back into the live `dp-spec.md`'s
   `## open_questions`, with a `blocks:` list naming what it stops.
4. That **un-approves** the spec — the plan the closure was built from no longer
   matches the live plan — so re-enter Step 1b: ask, get the ruling, re-approve,
   regenerate.

The ordering matters and is not stylistic: the attempt itself did not edit the
plan, so it records the same spec hash before and after. Editing the plan is a
separate, separately recorded event. Get that backwards and the record accuses
you of cheating on an entirely correct blocked exit.

The consequence worth internalizing: the elicitation contract is a **loop**, not
a pre-build gate. The same "I need something from you" queue serves a gap found
while authoring the spec and a gap found while running it.

## What the user hears

You are the **middleman**. The user does not need — and must not be given — any
of the internals above. The rules, in full, are R1–R8 in
[build-record.md](build-record.md#telling-the-user-the-middleman-rules), with
worked examples. The operating summary:

- **R1 — two classes only.** The user hears **blockers** ("I need something from
  you") and **concessions** ("I did something you should know about"). Nothing
  else reaches them.
- **R2 — who owns it decides, not how severe it is.** A hard error you can fix
  yourself is absorbed. A mere warning that is a concession is spoken.
- **R3 — everything else is one plain line of outcome.** Not a tour of what broke
  and got fixed. One line.
- **R4 — banned vocabulary.** Never say a stage name or number, a phase letter, a
  diagnostic code, a hash, "the IR", or the words `owner`, `origin`, `severity`,
  `provenance`, `not_reached`, "canonicalization". Say what happened in the
  user's own words.
- **R5 — never present green as right.** "Built and checked" — never "the numbers
  are correct."
- **R6 — a blocker is one sentence with the smallest possible ask**, plus what
  still works. Never a menu of internals, never options they did not ask for.
- **R7 — a concession states what was done, what it costs, and the alternative,
  in that order**, and offers to redo it the other way.
- **R8 — never assert "environment issue" without supervisor-reported evidence.**
  Say the honest thing: *"the build didn't complete and I can't yet tell whether
  that's my code or the machine — so I'm treating it as mine."* Fail-closed
  applies to speech as much as to classification.

**A green run carrying a concession the user has not heard is the worst state in
this design**, because it reads as finished. Say it, then claim.

## The commands

```bash
# what failed, at which step, and who owns it — instead of re-reading logs
python3 "$POCKET_HELPER_DIR/scripts/dp_diagnostics.py" record query --record <closure>/build-record.json --unresolved
python3 "$POCKET_HELPER_DIR/scripts/dp_diagnostics.py" record query --record <closure>/build-record.json --owner user

# did the plan move, is anything still open, is this actually finished
python3 "$POCKET_HELPER_DIR/scripts/dp_diagnostics.py" materialized --record <closure>/build-record.json \
    --lock <closure>/dp-spec.lock.json --spec <workflow>/dp-spec.md
```

`materialized` is the word. **Never `correct`.** It says the approved plan was
compiled, the compiled artifact ran, and it published. It says nothing whatever
about whether the numbers are right.

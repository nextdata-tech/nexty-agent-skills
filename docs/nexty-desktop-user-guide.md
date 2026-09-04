# Nexty Desktop User Guide

**For analysts working in Claude Cowork.**

You already know how to use an agent to get at your data. What you don't have is a way to get the *same* result next month, sliced differently, without redoing the work and without wondering whether last month's version used the same logic.

Nexty turns a job you do by hand into something that does it for you. It finds your data, applies your definitions, runs on your own machine, and costs less than redoing the thinking every time.

---

## Contents

- [Quickstart](#quickstart)
- [How it works](#how-it-works)
- [Phase 1: Bring a job to be done](#phase-1-bring-a-job-to-be-done)
- [Phase 2: Work the problem](#phase-2-work-the-problem)
- [Phase 3: Package it](#phase-3-package-it)
- [Phase 4: Run it forever](#phase-4-run-it-forever)
- [Key concepts](#key-concepts)
- [Prompt cookbook](#prompt-cookbook)
- [When something goes wrong](#when-something-goes-wrong)
- [Where things live](#where-things-live)

---

## Quickstart

### Install

**macOS 13 or later, Apple silicon (arm64) or Intel (x86_64).**

Download `nxd-desktop-0.0.0-*-macos-arm64.run` from **TODO**, make it executable and run it:

```
chmod +x nxd-desktop-0.0.0-*-macos-arm64.run
./nxd-desktop-0.0.0-*-macos-arm64.run
```

Restart Claude and check that Nexty Desktop is installed at **Settings → Connectors → nxd-desktop**.

### Run

Open a Cowork session and start the job loop by running `/nxd-run-job-loop`. You should see a screen that looks like this:

![start_screen.png](start_screen.png)

Not all questions are required, give as much guidance as you can. The more you give, the faster it will be to get a correct answer.

For example, if you want to analyze weather data, you might say the data product is about `Weather analysis` and the question to answer is:

> I want to analyze the last 30 days of weather in zip code 94941 to see which days of the week are the sunniest. Use the Open Meteo Weather API.

Claude will ask some clarifying questions. Iterate on the plan until you feel it's complete, then say
"plan approved, build the data product". Congratulations, you just built a data product.

---

## How it works

Nexty has an opinion about the order you do things in, and the order is the point.

```
   PHASE 1          PHASE 2           PHASE 3           PHASE 4
   Bring            Work              Package           Run

   a job you   →    it with      →    it up        →    it forever
   already do       Claude            so it can         for almost
   by hand          until it's        repeat            nothing
                    right
```

**[Phase 1](#phase-1-bring-a-job-to-be-done): Bring a job to be done.** Something real you've done at least once manually. You know what the right answer looks like, because you've produced it before.

**[Phase 2](#phase-2-work-the-problem): Work the problem.** Iterate with Claude in a session. Try things, get them wrong, correct definitions, argue about edge cases. This is exploration, and it's computationally expensive (e.g. LLM tokens): every question re-reads your data and re-derives the answer from scratch.

**[Phase 3](#phase-3-package-it): Package it.** When the answer is finally right and you know you'll need it again, Nexty captures the whole thing (your data, your definitions, your rules) as a **data product**.

**[Phase 4](#phase-4-run-it-forever): Run it forever.** The same question now costs almost nothing. Claude sends a small structured query, gets back a small table, and answers. It isn't re-reading your data or re-deriving your logic. It's looking it up.

### Why this saves you money

The gap between phase 2 and phase 4 is the reason Nexty exists.

| | Working the problem | Packaged |
| --- | --- | --- |
| What Claude computes | The whole derivation, every time | Nothing. It asks and reads |
| Token cost | Scales with your data and your logic | Scales with the size of the answer |
| Consistency | Depends on how you phrased it today | Same question, same number, always |
| Speed | Seconds to minutes | Immediate |

Exploring is the right way to *find* an answer. It's not a great way to *keep getting* one. A monthly report you rebuild by conversation costs you the full derivation twelve times a year, and can drift each time. Packaged, you pay that cost once.

**The rule:** explore freely, and the moment you catch yourself about to do the same reasoning a second time, stop and package it.

---

## Phase 1: Bring a job to be done

The single biggest predictor of success is what you bring. Not what data you have, but what job you want done.

**A good candidate:**

- You've done it before, by hand. You know what the right answer looks like.
- You'll do it again: monthly, weekly, every time a deal closes, every board meeting.
- You can state what it means. Not perfectly, but you can say "revenue excludes refunds" out loud.
- Getting it wrong would matter to someone.

**A bad candidate:**

- A one-off curiosity you'll never repeat. Just ask Claude; don't build anything.
- Something you've never done, so you can't tell a right answer from a plausible one.
- A question with no stable definition, where the answer moves because the question does.

Describe the job, not the plumbing. This is a good brief:

> Every month I produce revenue by region and product category with the top 20 customers, excluding refunds and internal test accounts. It takes me half a day. Last month came to $4.2M.

Note what's in it: the outcome, the rules, the cadence, and a number you can check against. Note what isn't: any mention of where the data lives or what format it's in. Nexty works that out.

### What Nexty can reach

Nexty finds and retrieves data for you rather than waiting to be handed a file. It can pull from:

- **Databases** you already use: Snowflake, Postgres, and others. Give it the connection once.
- **APIs**, including internal services and third-party ones.
- **Files and exports**, wherever they sit on your machine or in a shared folder.

Ask it what it sees:

> What data can you get to?

> Look at our warehouse and tell me what's in the sales schema.

If it needs a credential or a connection detail, it asks for that specific thing and nothing more. Credentials stay on your machine.

---

## Phase 2: Work the problem

This is the phase where being picky pays, because every correction here is one you'd otherwise make forever.

Talk to Claude the way you'd brief a colleague. Give it the target you already know. Then push back on what comes out:

> That top customer is a duplicate. We have them under two account IDs.

> You're including our own staging environment orders. Those aren't real.

> Growth should be year over year, not against last quarter.

Ask it to show its reasoning when a number surprises you:

> Walk me through what that's counting.

**Don't skip ahead to packaging.** A packaged product built on a definition you hadn't finished arguing about is worse than no product. It makes a wrong number repeatable and gives it an official-looking home.

You'll notice this phase is slow and each question costs real tokens. That's expected. You're paying for discovery, once.

---

## Phase 3: Package it

When the answer is right:

> This is right. Turn it into something I can reuse.

### The plan

Before building anything, Nexty writes out **the plan**: plain English, your job written down. It covers what the product is for, what questions it answers, what your terms mean, what rules always apply, and anything Nexty couldn't work out without you. We call this the data product blueprint.

You don't need to understand its structure, but if you're curious about the details, you can review the plan at any time. You can check two things:

1. **Your corrections are in it.** Everything you argued about while working the problem should be written down here. If you told Claude that refunds don't count and there's nothing about refunds in the plan, say so now.
2. **The open questions are answered.** Nexty lists what it couldn't resolve on its own. These are the assumptions that will quietly shape every future answer.

It's yours to change:

> "Enterprise account" should mean ACV over $50k **or** headcount over 1,000, not both.

> Add a note that we haven't decided how to treat the EMEA account merge.

### Approving

> That's right. Build it.

Approving means you agree with the description read back to you, not that you audited a file. Cowork asks you to confirm before the build actually runs, which is the last cheap moment to change your mind.

The build takes a few minutes. Nexty retrieves your data, builds the product, runs it, and checks it. That's not a hang. It's the one-time cost that makes everything after it free.

---

## Phase 4: Run it forever

### Asking

> What was revenue by region last quarter?

> Top 10 customers by revenue, this year versus last.

> Northeast versus Southwest, month by month.

Claude shows you what it actually asked the product alongside the answer. **Read that part.** If your question and its query don't match, say so and it'll correct.

### Coming back later

Close your laptop, come back in three weeks, new session:

> Open my orders product and show me last week's revenue.

Nexty finds the data product and reconnects in seconds. Your terms, rules, and decisions are all still there.

### Sharing

After each build Nexty writes a **blueprint page**: one self-contained markdown file describing the data product, its logic, its definitions, and what it promises.

> Give me the blueprint for this data product.

Email it, post it, attach it to a deck. It answers "where does this number come from?" without a meeting.

### When the job changes

It will. Revenue gets redefined, a region splits, a new product line appears. Drop back to phase 2 for the bit that changed:

> Marketplace revenue needs to be reported separately from direct now. Update the product.

Nexty amends the blueprint, shows you what changed, and rebuilds. You are not starting over.

---

## Key concepts

Six ideas. Once these land, the rest is obvious.

### Measures and dimensions

A **measure** is a number: revenue, order count, average basket size, days to close.

A **dimension** is a way of slicing it: region, month, product category, rep, segment.

Every question is some measures cut by some dimensions. "Revenue by region last quarter" is one measure, one dimension, one filter. Nexty builds this vocabulary from your data and your questions, and then the product speaks it.

> What can I ask this product about?

### Grain

**Grain** is what one row means. One order? One order line? One customer per month?

This is the most common source of a wrong number that still looks completely plausible. Sum a value repeated across order lines and you double-count it, and nothing about the result looks alarming. Nexty works out the grain and tells you what it decided. Spend ten seconds checking. If the grain is wrong, everything downstream is wrong.

### Terms

Your definitions, written into the product.

> An "active customer" ordered in the last 90 days. A "qualified lead" scores above 70 **and** has a booked meeting.

Once a term is in the product, everyone asking gets your definition instead of inventing their own. This is most of the value, and it's the part people skip.

### Standing rules vs. filters

Where consistency is won or lost.

A **filter** scopes one question. *"Just Q3."* *"Just the Northeast."* You choose it each time.

A **standing rule** always applies. *"Refunds never count as revenue."* *"Internal test orders are not orders."*

The test: **imagine a colleague who never heard the rule, asking with no filters.** If their number would be *wrong*, not merely broader but wrong, it's a standing rule and belongs inside the product. If their number would just be *bigger*, it's a filter.

Get this right and the product is safe to hand to anyone. Get it wrong and it's a trap only you know how to avoid.

Be explicit about which you mean:

> Exclude intercompany transfers from revenue **permanently, not just in this query.**

### Projects

Each product has a project name. That's your handle for it. Everything else (where the data came from, how it was built, what it decided) Nexty remembers for you.

### Exploring vs. asking

Worth naming, because it's the difference between the phases.

**Exploring** is open-ended: Claude reads your data and reasons about it. Powerful, expensive, and the answer depends partly on how you asked.

**Asking a product** is bounded: Claude sends a structured query and reads back a small table. Cheap, fast, and the answer depends only on what you asked for.

Neither is better. Explore to discover; package to repeat.

---

## Prompt cookbook

Copy these and change the nouns.

### Finding data

> What data can you get to?

> Look at our warehouse and tell me what's in the sales schema.

> Is there anything in here that tracks support tickets?

### Working the problem

> I want to explore tickets in our linear.app tracking system to see what open tickets exist for the project pocket. I want to use AI to examine them and prioritize them.

> Help me rank job applicant candidates in Ashby by their resume and cover letter. I want to see which ones are most likely to succeed in the role.
 
> Find our support tickets and show me resolution time by team and priority. I want to spot which categories are getting slower. Last quarter's median was 14 hours, so we can check against that.

> Pull revenue and pipeline by rep and stage, monthly, from the warehouse.

> Here's our churn metric spec [attach]. Work through it with me and tell me what the doc left ambiguous.

> Combine orders with the customer list so I can see revenue by segment and signup cohort.

> Walk me through what that number is counting.

### Packaging

> This is right. Turn it into a reusable product.

> Show me the plan again. I want to check the definitions.

> "Enterprise account" means ACV over $50k or headcount over 1,000. Use it everywhere.

> Add an open question: we haven't decided how to treat the EMEA account merge.

### Using it

> Revenue by region, last quarter.

> Top 10 customers by revenue, this year versus last.

> What questions can this product answer?

> What terms are defined in here?

> What did you assume when you built this?

That last one is a good monthly habit. It surfaces decisions made on your behalf while you weren't watching.

### Fixing and changing

> That revenue figure looks too high. Walk me through what it's counting.

> Marketplace revenue should be reported separately from direct now. Update the product.

> Exclude intercompany transfers permanently, not just in this query.

### Sharing

> Generate the release page and tell me where to find it.

> Export this product so I can send it to a colleague.

---

## When something goes wrong

**Nexty can't find the data you meant.** Ask what it can see: *"what data can you get to?"* If the source isn't listed, it needs a connection or a credential. Tell it where to look and it'll ask for the specific thing it needs.

**You attached a file and Nexty ignored it.** Cowork runs its own workspace, separate from your Mac, and Nexty runs on your Mac. An attachment helps Claude understand your data's shape while you work, but for a build, Nexty needs the real source: a connection, or a file path on your own machine.

**A number looks wrong.** Ask Claude to show its work: *"walk me through how that was calculated."* Nine times out of ten it's the grain or a missing standing rule.

**The build failed.** Nexty reports what broke and what it's doing about it. Most failures are a data surprise: a column that's text where numbers were expected, a date format that changes halfway through. Tell it what you know about your data and it'll adjust.

**It won't answer a question.** That's deliberate. If the product can't answer honestly, Nexty says so rather than guessing. Ask what's missing:

> Why can't you answer that? What would you need?

**You're being asked to approve a lot.** Cowork confirms before anything consequential. If a build takes several approvals, approve them. That's the design, not a fault.

**Something looks stuck.** The menu bar dot tells the truth: green healthy, amber working, red means **Settings → Diagnostics**.

---

## Where things live

|                        |                                                              |
|------------------------|--------------------------------------------------------------|
| `~/nxd-jobs/`          | One folder per data product. Everything Nexty built for you. |
| Menu bar dot           | Green healthy, amber working, red needs attention.           |
| Settings → Connections | Data connections, and the Claude connection.                 |

Nothing is hidden. Open these folders, read them, back them up. Your data and credentials stay on your machine.

---

## What to do next

1. Pick one job you did by hand this month and will do again next month. Just one.
2. Work it in a session until the number matches the one you already know.
3. Package it, and ask again next month for almost nothing.
4. Then add your terms. That's where a personal tool becomes a team one.

The habit worth building: when you notice yourself about to do the same reasoning a second time, that's the signal. Stop exploring and package it.

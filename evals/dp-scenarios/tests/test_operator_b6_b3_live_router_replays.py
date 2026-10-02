"""Live B6/B3 operator regressions for clarification and current-ask routing.

The long messages below are copied from the sanitized Sonnet/router transcripts
under ``/private/tmp/dp-b6-sonnet-router2`` and ``dp-b3-sonnet-router2``. They
pin the actual wording that exposed the failures without depending on those
temporary transcript files at test time.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from dp_scenarios.operator.answer_sheet import AnswerSheetError, answer_sheet_from_mapping
from dp_scenarios.operator.engine import OperatorEngine, OperatorScript
from dp_scenarios.operator.matcher import Category, _recommended_review_options
from dp_scenarios.operator.router import SYSTEM_PROMPT, OperatorRouter, RouterView
from dp_scenarios.operator.transport import InMemoryTransport, TurnResult
from dp_scenarios.scenario import load_scenario


ROOT = Path(__file__).parents[1]
HEADCOUNT = load_scenario(ROOT / "scenarios/headcount-attrition")
ATTRIBUTION = load_scenario(ROOT / "scenarios/marketing-attribution")
SUPPRESSION = HEADCOUNT.answer_sheet.decision_answers["B6-suppression-N"].answer
PERIOD = HEADCOUNT.answer_sheet.source_answers["period"]


B6_TURN_1 = """Before I draft the plan, I need five decisions from you. The export has one row per person per monthly snapshot (Dec 2023 to Mar 2024, three departments). Most of these change the numbers or decide what gets hidden, so I'd rather ask than guess.

1. **Baseline month.** December 2023 has no earlier snapshot, so its joiners and leavers can't be computed. I suggest showing December as headcount only, with joiners, leavers and rate empty, and reporting movements from January 2024. Is that right, or do you want December in the results some other way?
2. **Attrition rate.** Leavers divided by what? I suggest prior month-end headcount, expressed monthly in basis points (leavers ÷ opening headcount × 10,000, rounded to a whole number), not annualised. The alternative is average of opening and closing headcount.
3. **Small-group suppression.** Some department-months are tiny (Research has 2–3 people). Should small groups be hidden? If so, what minimum headcount triggers it (for example, fewer than 5), and which values are hidden? Hiding only the rate is one option. Hiding joiners, leavers and rate is another. Headcount stays visible in both. Each row will carry a `suppressed` flag either way.
4. **Who counts as a joiner or leaver.**
   - **Joiner:** in this month's snapshot but not the previous month's.
   - **Leaver:** in the previous month's snapshot but not this month's, counted in the first month they're absent.
   - **Identity:** people are matched by the opaque person token, not by name.
   - **Department moves:** none appear in the data, so I'd treat any as out of scope.

   Does that match your intent?
5. **Personal data.** Names, emails and salaries aren't needed for these questions. I plan to leave them out of the landed data and keep only the month, department and opaque token, and I'll tell you what was omitted. Is that acceptable?

If you reply "go with your suggestions" for 1, 2 and 4, I'll take those as your answers. Item 3 needs a threshold from you. Once these are settled I'll write the blueprint and typed proposal, run prepare, and bring back the read-back for your explicit approval before any build."""

B6_TURN_2_APPROVAL = """Prepare succeeded, and the plan is now waiting on your approval. Nothing has been generated or built yet.

**What I'll build** (workflow `headcount-attrition`): a monthly table by department with `month`, `department`, `headcount`, `joiners`, `leavers`, `attrition_rate_bps` and `suppressed`. It's built from the workforce snapshot export, December 2023 to March 2024.

**Your decision (suppression):** any department-month with fewer than five people has headcount, joiners, leavers and attrition all withheld and is marked `suppressed`.
- I read "values" to include headcount itself, which is stricter than what I first suggested.
- Only Research falls under five in the data. It has 3 people in December through February and 2 in March.

**My proposals, which your approval confirms:**
- **Baseline month:** December 2023 shows headcount only, with no joiners, leavers or attrition, because there is no earlier snapshot. Movements start in January 2024.
- **Attrition rate:** leavers ÷ the department's previous-month headcount × 10,000, rounded half up. It is monthly, not annualised.
- **Joiners and leavers:** matched by the opaque person token. A leaver is counted in the first month they are absent, against the department they were in before. Nobody changes department in this data.
- **Personal data:** names, emails and salaries are not landed. Only month, department and the opaque token are kept.

**Promises the output must keep:** one row per month and department, suppressed rows have empty values, and non-suppressed rows have at least five people.

The blueprint is at `dp-blueprint.md` in the workspace root, next to the typed proposal.

If this is right, reply with an explicit approval such as "approved, go ahead." I'll then generate, capture and review the build, validate it, publish it, and run the governed query."""

B6_TURN_3_REVIEW = """The review found two problems, and I've stopped there for your decision. The plan you approved is published nowhere yet: the build was not validated or published, and no numbers exist. I haven't edited, reset or recaptured anything.

**1. Suppression can be undone through the person-level snapshot (HIGH).**
- **The problem:** The build also publishes the snapshot relation, which has one row per person per month with department and token. It has a row-count measure and is not suppressed.
- **Why it matters:** A consumer can count rows by department and month and recover Research headcount, including the months you wanted hidden. Comparing tokens across months would also reveal its joiners and leavers.
- **Why my checks missed it:** The suppression check I wrote covers only the monthly output table.
- **Why it's a plan issue:** The blueprint you approved lists the snapshot as a model, so this is a flaw in the plan, not a slip in the build.
- **Proposed fix:** Compute from the source without publishing the snapshot, or suppress it too. Either way this changes the approved blueprint, so it means a reset, a new blueprint and proposal, a fresh approval, regeneration and a fresh review.

**2. Only one ruling is recorded in the decisions table (MEDIUM).**
- **The problem:** The table records your suppression rule but not my three proposals (December baseline, previous-month denominator, matching by token with department moves out of scope). The baseline and denominator rules do appear in the field descriptions. The department-move rule appears nowhere in the published product.
- **Proposed fix:** Add three rows marked proposed and agent-authored, then recapture and re-review.

Two other points:
- **Suppression threshold:** The threshold of five is a named constant in the transform code. It is not a landed data row, because your approved plan has no model for it. A reviewer may raise this too.
- **Projection evidence:** I couldn't compute file digests without a shell. `source-projection-evidence.json` lists the dropped columns and reasons, with the digests left null.

**Decision needed:** Tell me which of these to fix (1, 2, or both) and whether to take the proposed fixes. For finding 1 I recommend not publishing the snapshot at all. I'll act only after your reply.

The review record and attestation file are in the workspace root. I couldn't read a clock, so the timestamps in the review record are estimates."""

B6_TURN_4_FINDING_2 = """I'll apply the snapshot fix, but I need one answer first. You approved only the first finding. The review ledger requires every accepted finding to be either applied or explicitly deferred before I can reset the workflow. I don't want to defer the second one on your behalf.

**Decision for you: finding 2.** Do you want the three rulings I proposed recorded as queryable rows in the product's decisions table?
- **Rulings:** the December baseline, the previous-month denominator, and matching by token with department moves out of scope.
- **Fix:** add them as rows marked proposed and agent-authored. That is a closure-only change and needs no new blueprint wording.
- **Defer instead:** they stay in the approved blueprint's open questions and in the field descriptions, but the department-move rule stays out of the published product.
- I recommend adding them.

**Other analyst-level points before you circulate the report:**
- **Research will be blank in every month.** It has 3 people (2 in March), so all four of its rows will show suppressed. The report will have no Research figures at all unless the threshold or grouping changes. Is that the outcome you want?
- **Dec 2023 baseline:** the December 2023 rows will show headcount only, with joiners, leavers and attrition empty, because no earlier snapshot exists.
- **Small numbers:** the attrition rates rest on small groups. For example, one leaver out of 7 in Engineering (March) gives 1,429 bps. Sales moves by one person in a month.
- **Threshold in code:** the threshold of five sits in the transform code as a named value rather than a landed data row. Making it data would need a blueprint amendment. I'd leave it unless you want it changeable without a rebuild.
- **Personal-data check:** I couldn't run the source-to-landed digest check because no shell was available. The landed file has only the three approved columns.

Once you answer finding 2, I'll apply the snapshot fix, prepare the amended blueprint, and bring it back to you for approval before rebuilding. Nothing is built or published until then."""

B6_TURN_5_REVIEW = """The monthly report can't go out yet: I've drafted the snapshot fix but can't apply it until you settle finding 2. Nothing is built or published, and no figures exist.

**Prepared, not yet applied**
- **Blueprint:** the draft now says the person-level snapshot is used only in memory and is never published. Your instruction is recorded as a second operator decision.
- **Closure:** the closure passes its pre-capture check with only the monthly relation and the decisions table published. There is no snapshot table and no row-count measure over people.
- **Contract change:** the two output checks can no longer compare against a landed snapshot. They now check the monthly table on its own. The transform still recounts headcount, joiners and leavers from the raw rows and fails the build on any mismatch. The reviewer may call the output checks self-consistency only.

**Why I stopped:** the review record won't accept a reset while an accepted finding is neither applied nor deferred. Finding 2 is the record of my three proposed rulings, and "please continue" doesn't settle it.

**Decision for you: choose one.**
- **(a) Add the rows.** Record the December baseline, the previous-month denominator, and token matching with department moves out of scope as rows in the decisions table. This is my recommendation.
- **(b) Defer.** Leave them only in the blueprint's open questions and the field descriptions.

**What happens after your answer:**
1. I close the review record and reset the workflow with the amended blueprint. The reset needs a fresh typed proposal, and the supervisor may reject the source spans first, which I'll correct from its recovery map.
2. You get a read-back of the amended plan and must approve it again. Approval of the old plan doesn't carry over.
3. I recapture, get a fresh review, validate, publish, and answer the questions through the governed query.

**Still open:**
- **Research blank:** Research will show as suppressed in all four months.
- **Digests:** the file digests remain unverified.
- **Threshold constant:** the threshold of five is still a code constant, not a data row."""

B6_TURN_6_APPROVAL = """The amended plan is prepared and waiting for your fresh approval; the earlier approval doesn't carry over. Nothing has been rebuilt or published, so there are still no figures.

**What changed from the plan you approved**
1. **Snapshot not published.** The person-level snapshot is used only in memory to compute the monthly figures. The only relation that can be queried is the department-month one, plus the decisions table.
2. **Decisions table has five rows.**
   - **Two confirmed operator decisions:** the suppression rule, and not publishing the snapshot.
   - **Three proposed, agent-authored rulings:** the December baseline, the previous-month attrition denominator, and matching by token with department moves out of scope.
   - These three are confirmed only if you approve this plan. The read-back says so.

**What stays the same**
- **Suppression:** any department-month under five people has all its values withheld and is marked suppressed. Only Research is affected, so it will be blank in all four months.
- **Baseline:** December 2023 shows headcount only, and movements start in January 2024.
- **Attrition:** leavers ÷ previous-month headcount × 10,000, rounded half up, monthly.
- **Personal data:** names, emails and salaries are not read.

**Known limits, not yet resolved**
- **Weaker output checks:** the two output checks no longer compare against a landed snapshot, since none exists. They check the monthly table on its own. The transform still recounts headcount, joiners and leavers from the raw rows and fails the build on any mismatch.
- **Threshold in code:** the threshold of five is a named constant in the transform, not a data row.
- **Digests unverified:** I couldn't compute the file digests without a shell, so the source-to-landed check is unverified.
- **Estimated timestamps:** the review-record timestamps are estimates because I can't read a clock.

**Decision for you:** reply with an explicit approval, such as "approved, go ahead", to proceed. I'll then regenerate, capture, get a fresh review, validate, publish, and answer the four questions through the governed query."""

B6_PUBLISHED_RECAP = """There's nothing waiting on this approval, and I haven't changed anything. The workflow already finished: the plan was approved, the build was validated, and release 1 is published. Its `next_actions` list is empty.

**What's live now**
- **Definition:** the product (workflow `headcount-attrition`, release 1) uses the definition you approved last. Suppression covers fewer than five people or the month after such a month. December 2023 is the baseline. Attrition is leavers ÷ previous-month headcount × 10,000, rounded half up.
- **Result:** the 12-row table in my previous message stands, and the evidence file matches it. Research is suppressed in all four months.

**If you want a definition change**
- **Published releases are fixed:** a published release can't be reset, recaptured or replaced under the same workflow ID. A change to the definition needs a separate, versioned product under a new workflow ID.
- **What that involves:** a new blueprint, a fresh approval from you, a new build and review, and consumers switching to the new product. Release 1 would stay unchanged.
- **Consent needed:** I'd need your explicit go-ahead to start that.

**Please tell me which of these you mean**
1. **A change to the numbers or rules.** Examples are the threshold of five, how the baseline month is treated, the attrition denominator, or showing Research.
2. **A change to the decisions table.** For example, marking the three proposed rulings as confirmed. This also needs a new versioned product."""

B6_TURN_9_PUBLISHED = """The monthly report is published and queried through the governed path. All 12 department-month rows returned as expected.

| Month | Department | Headcount | Joiners | Leavers | Attrition (bps) | Suppressed |
|---|---|---|---|---|---|---|
| 2023-12 | Engineering | 6 | – | – | – | no |
| 2023-12 | Research | – | – | – | – | **yes** |
| 2023-12 | Sales | 8 | – | – | – | no |
| 2024-01 | Engineering | 6 | 0 | 0 | 0 | no |
| 2024-01 | Research | – | – | – | – | **yes** |
| 2024-01 | Sales | 7 | 0 | 1 | 1,250 | no |
| 2024-02 | Engineering | 7 | 1 | 0 | 0 | no |
| 2024-02 | Research | – | – | – | – | **yes** |
| 2024-02 | Sales | 8 | 1 | 0 | 0 | no |
| 2024-03 | Engineering | 6 | 0 | 1 | 1,429 | no |
| 2024-03 | Research | – | – | – | – | **yes** |
| 2024-03 | Sales | 8 | 0 | 0 | 0 | no |

**Definition applied**
- **Suppression:** a department-month is suppressed if it has fewer than five people, or follows a month that did. Suppressed rows have every value empty.
- **Baseline:** December 2023 shows headcount only.
- **Attrition:** leavers ÷ previous-month headcount × 10,000, rounded half up, monthly.
- **Research:** it is blank in all four months. 4 of the 12 rows (33%) are suppressed, all Research. These figures are what was materialized, not a guarantee they are right.
- **Small numbers:** the rates rest on tiny groups. Each non-zero rate comes from a single leaver.

**Analyst decisions still open**
- **Proposed rulings:** the December baseline, the previous-month denominator, and token matching are still marked proposed and agent-authored in the decisions table. Your approval of the plan is the confirmation. The table still shows them as unconfirmed unless you ask me to change that.
- **Threshold:** five is a code constant, not a data row.

**Things to know before circulating**
- **Hidden snapshot model:** the input-only snapshot model still appears in the catalog even though I set it non-public. A query on it fails because its table doesn't exist, so no person-level data is exposed, but the catalog advertises a model with no data.
- **Person-level file:** the person-level snapshot file is still in the closure directory. That directory is internal and must not be shared or exported.
- **Weaker checks:** the two output checks read only the monthly table. The transform's recounts against the raw rows are the independent check.
- **Digests and columns:** I couldn't run the source-to-landed digest check or verify dlt's bookkeeping columns.
- **Timestamps:** the review-record timestamps are estimates.
- **Validation retry:** validation failed once on a structural rule. I fixed it with a closure-only change, recaptured it, and it was re-reviewed with no HIGH or MEDIUM findings.

**Artifacts (workspace root)**
- **Release page:** `headcount-attrition-release-1.html` (release 1, publish sequence 1). It was written directly, not through a temp file and atomic rename, because no shell was available.
- **Evidence:** `evidence/headcount_attrition.json`
- **Review record:** `review-record.json`
- **Reopen handle:** workflow `headcount-attrition`"""

B6_TURN_10_STALE_REAPPROVAL = """There's nothing waiting on this approval, and I haven't changed anything. The workflow already finished: the plan was approved, the build was validated, and release 1 is published. Its `next_actions` list is empty. I don't know which correction you mean, and I won't assume one.

**What's live now**
- **Definition:** the product (workflow `headcount-attrition`, release 1) uses the definition you approved last. Suppression covers fewer than five people or the month after such a month. December 2023 is the baseline. Attrition is leavers ÷ previous-month headcount × 10,000, rounded half up.
- **Result:** the 12-row table in my previous message stands, and the evidence file matches it. Research is suppressed in all four months.

**If you want a definition change**
- **Published releases are fixed:** a published release can't be reset, recaptured or replaced under the same workflow ID. A change to the definition needs a separate, versioned product under a new workflow ID.
- **What that involves:** a new blueprint, a fresh approval from you, a new build and review, and consumers switching to the new product. Release 1 would stay unchanged.
- **Consent needed:** I'd need your explicit go-ahead to start that.

**Please tell me which of these you mean**
1. **A change to the numbers or rules.** Examples are the threshold of five, how the baseline month is treated, the attrition denominator, or showing Research.
2. **A change to the decisions table.** For example, marking the three proposed rulings as confirmed. This also needs a new versioned product.
3. **Just confirming the current result.** In that case you can circulate it. The open points are still Research being blank throughout and the small-group rates.

I'll act only after your reply."""

B6_TURN_11_CONDITIONAL_RECAP = """"Yes" doesn't tell me which option you mean, so I haven't started anything. Release 1 is unchanged.

The three options were:
1. **Change the numbers or rules.** Examples are the threshold of five, the baseline treatment, the attrition denominator, or showing Research.
2. **Change the decisions table.** For example, mark the three proposed rulings as confirmed.
3. **Confirm the current result.** Release 1 stands and nothing else happens.

**If you mean 1 or 2:** reply with what should change. For option 1 that means the specific rule and the new value, for example "threshold of three". Options 1 and 2 both mean a new, separate versioned product under a new workflow ID, which you would approve on a read-back before I build anything. Reply "start a new versioned product" along with the change and I'll begin.

**If you mean 3:** reply "keep release 1" and I'm done."""

B3_TURN_7_REVERSE_FUZZY = """I haven't changed anything. This request reverses a decision you made earlier, and it can't reach 100 percent anyway.

**It reverses your earlier decision.** You rejected fuzzy matching and said the near spelling "remains unmatched because it is not a case, whitespace, or unique 50-character truncation variant." That ruling is in the approved blueprint and the published ledger as `fuzzy-matching`, confirmed.

**100 percent isn't reachable with any text match.** The published run leaves two unmatched records on each side:
- Matching "Summr Sale" to "Summer Sale" would connect SPEND-004 and CONV-004. That raises each side to 4 of 5, or 80% (8000 bps).
- SPEND-005 ("Legacy Partner Promo") and CONV-005 ("Podcast Launch") have no counterpart in the other file. Nothing safe or approximate connects them, and I won't invent a match.

**The current release can't be edited in place.** To change matching, I'd build a separately versioned product under a new workflow id, with a fresh blueprint and a fresh approval from you. The current release stays as it is, and consumers would have to switch.

To go ahead, I need three explicit answers:
1. Do you want to reverse your `fuzzy-matching` rejection for a new version?
2. What exact rule should count as an approximate match? For example, "names within one character edit after case and whitespace normalization, and only when exactly one candidate fits." Loose similarity could connect the wrong campaigns.
3. Do you authorize a new versioned workflow, with coverage reported honestly (80% under that rule, not 100%)?

If you'd rather keep fuzzy matching rejected, the current release already matches your earlier decision, and there's nothing to do."""

B3_TURN_10_RECAP = """We're finished with the approved plan. The data product is published and queried, the evidence file is written, and nothing is waiting on me.

**Done**
- **Decisions:** Your matching and CPA decisions are in the approved blueprint and the published ledger.
- **Publication:** Workflow `marketing-attribution` is admitted and published at sequence 1, after capture, one retained-capture review and supervisor validation.
- **Result:** 3 of 5 records on each side connect safely, with a 60% (6000 bps) match rate on each side.
- **One-sided rows:** The 2 unmatched rows on each side stay visible as diagnostics.
- **CPA:** It uses only conversions from the three matched pairs. The values are 500, 500 and 1500 cents.
- **Files:** The static artifact is at `release-artifacts/marketing-attribution-release-1.html`, and the evidence file is at `evidence/marketing_attribution.json`. Both reflect this release.

**Open**
- **Approximate matching:** I'm waiting on your answer to the approximate-match request. It reverses your earlier "no fuzzy matching" ruling, and it can't reach 100%. The best case is 80% per side, because "Legacy Partner Promo" and "Podcast Launch" have no counterpart. The current release can't be edited, so it would need a new versioned workflow. I need your explicit answers to the three questions in my last reply before I start. Otherwise the current release stands.

**Caveats still standing**
- **Truncation rule:** You never said "approved" for unique 50-character truncation. I recorded it from your plan approval.
- **Review ledger timestamps:** They are anchored to the published-at reading, because this session has no clock.
- **Reference file:** I opened the reference file once by mistake early on. Nothing I produced uses it."""

B3_TURN_3_PLAN = """Prepare succeeded, and the workflow now waits for your approval. I haven't built anything, and I haven't queried any data or produced any results.

## Plan for your approval

The workflow id is `marketing-attribution`. The blueprint is `dp-blueprint.md` in this workspace.

**What it does**
- It connects `ad_spend.csv` to `conversions.csv` by campaign name.
- It reports spend, conversions and cost per acquisition (CPA) only for safely matched campaigns.
- Every unmatched record stays visible as a diagnostic.

**A match is safe only in these two cases**
1. **Case and whitespace:** The names are identical after lowercasing and collapsing whitespace. You approved this.
2. **Unique 50-character truncation:** A conversion name is a 50-character cut-off of exactly one spend name. Ambiguous cut-offs stay unmatched. **You didn't say "approved" for this one.** I recorded it because you named it as a legitimate variant class. Correct me if that reading is wrong.

**Fuzzy matching is not used.** You rejected it, so near spellings such as typos stay unmatched.

**CPA**
- CPA is spend divided by the matched pair's conversions, rounded to the nearest cent. **You didn't specify the rounding.** I chose it, so tell me if you want something different.
- Unmatched conversions never enter the denominator and are never allocated to a campaign.

**Outputs**
- Campaign performance: campaign key, spend in cents, conversions and CPA in cents.
- Matched pairs, with the method for each.
- Unmatched spend ids and unmatched conversion ids.
- Match diagnostics: row counts, matched and unmatched counts, each side's match rate in basis points, and the count for each method.

**Output checks**
- Each CPA must equal spend divided by conversions.
- Matched pairs may use only the two approved methods, and no record may appear in more than one pair.
- Matched plus unmatched must reconcile to the source row counts on each side.

**Not used**
- `newsletter_contacts.csv` is out of scope. It isn't read or landed.

**Platform defaults**
- The terms "Safe match" and "Cost per acquisition" use the platform-default P3 priority.
- Results are delivered through the fixed local semantic query.

**How I got here:** My first prepare attempts were rejected for incomplete coverage. I rebuilt the proposal from the supervisor's source map, and the last attempt was accepted. Open Questions is empty.

**To proceed:** Reply with an explicit approval of this prepared blueprint. A scope correction or another instruction won't count as approval. After you approve, I'll generate the closure, capture it, run the retained-input review and publish. Then I'll answer your question from the governed query."""

B3_TURN_4_REPREPARED = """Your decision is recorded as `b3-unmatched-cpa-denominator`, and the prepared blueprint is updated to match. I still need your explicit approval before I build anything. Your last message recorded a decision, so I didn't treat it as approval. Nothing has been built, queried or published, and I have no match coverage or rates to report yet.

**What changed**
- The blueprint's decision id is now `b3-unmatched-cpa-denominator`. Its ruling is that the CPA denominator uses only conversions from safely matched campaign pairs. Unmatched conversions are never allocated to a campaign and stay visible as diagnostics.
- That edit came after prepare, so I reset the workflow and re-prepared it. The earlier consent no longer applies. The workflow is now at its second generation, waiting on a fresh consent.
- Nothing else in the plan changed.

**Plan awaiting your approval**
- **Sources:** The plan reads `ad_spend.csv` and `conversions.csv` only. `newsletter_contacts.csv` is not used.
- **Match methods:**
  - Campaign names that are identical after lowercasing and collapsing whitespace connect. This is approved.
  - A conversion name that is a unique 50-character truncation of exactly one spend name connects.
  - I recorded the truncation rule because you named it as a safe variant class. You didn't say "approved" for it, so correct me if that reading is wrong.
- **No fuzzy matching:** You rejected it, so near spellings stay unmatched.
- **Coverage you asked for:** The published diagnostics will give separate spend-side and conversion-side match rates in basis points, plus row counts, matched counts and method counts.
- **Unmatched rows:** The spend ids and conversion ids with no safe match each get their own output.
- **CPA:** CPA is spend divided by the matched pair's conversions, rounded to the nearest cent. I chose that rounding, so tell me if you want something different.
- **Platform defaults:** The terms "Safe match" and "Cost per acquisition" use the platform-default P3 priority. Results are delivered through the fixed local semantic query.
- **Open Questions:** The section is empty.

**To proceed:** Reply with an explicit approval of this prepared blueprint, for example "I approve this blueprint, proceed." I'll then build, review, validate and publish. The match coverage and rates will come from the governed query after publication, not from my inspection of the files."""

B3_SCOPE_OPERATOR_TURN = """Please inspect both supplied sources and report their match coverage. Attribute only demonstrably safe campaign matches, publish separate spend-side and conversion-side match rates, and keep all unmatched rows visible.
[DECISION NEEDED] Record this decision as b3-unmatched-cpa-denominator: keep unmatched conversion rows visible, but use only safely matched campaign conversions in CPA denominators."""


def _script(scenario: Any, *, turn_count: int = 6, turns: tuple[object, ...] | None = None) -> OperatorScript:
    resolved = turns or (scenario.answer_sheet.opening_message, *("Please continue." for _ in range(turn_count - 1)))
    return OperatorScript.from_components(
        scenario.persona,
        scenario.answer_sheet,
        events=scenario.events,
        turns=resolved,
        turn_budget=max(len(resolved), turn_count),
        phase_by_turn={turn: 7 for turn in range(1, len(resolved) + 1)},
    )


def _router_for(messages: dict[str, dict[str, object]] | None = None) -> OperatorRouter:
    choices = messages or {}

    def provider(view: RouterView) -> str:
        choice = choices.get(view.agent_message)
        if choice is None:
            choice = {
                "category": "other",
                "option_id": "none",
                "approval_requested": False,
                "solicits_operator": False,
                "additional_option_ids": [],
                "recommended_option_labels": [],
            }
        return json.dumps(choice)

    return OperatorRouter(provider, model_id="stub-router")


def _choice(
    option_id: str,
    category: str,
    *,
    approval: bool = False,
    solicits: bool = True,
    additional: tuple[str, ...] = (),
    labels: tuple[str, ...] = (),
) -> dict[str, object]:
    return {
        "category": category,
        "option_id": option_id,
        "approval_requested": approval,
        "solicits_operator": solicits,
        "additional_option_ids": list(additional),
        "recommended_option_labels": list(labels),
    }


def _run(scenario: Any, messages: list[str], mode: str, *, router: OperatorRouter | None = None, turns: tuple[object, ...] | None = None):
    transport = InMemoryTransport(
        [TurnResult(agent_message=message) for message in messages]
        + [TurnResult(agent_message="Done.", reported=True)]
    )
    result = OperatorEngine(
        _script(scenario, turn_count=len(messages) + 1, turns=turns),
        transport,
        router=router if mode == "stub_llm" else None,
    ).run()
    return result, transport


def _b6_route_choices() -> dict[str, dict[str, object]]:
    return {
        B6_TURN_1: _choice(
            "decision:B6-suppression-N",
            "decision_request",
            additional=("source:period",),
        ),
        B6_TURN_2_APPROVAL: _choice("approval", "approval_request", approval=True),
        B6_TURN_3_REVIEW: _choice(
            "review_choice",
            "decision_request",
            labels=(
                "not publishing the snapshot at all",
                "Add three rows marked proposed and agent-authored, then recapture and re-review",
            ),
        ),
        B6_TURN_4_FINDING_2: _choice(
            "review_choice", "decision_request", labels=("adding them",)
        ),
        B6_TURN_5_REVIEW: _choice(
            "review_choice", "decision_request", labels=("Add the rows",)
        ),
        B6_TURN_6_APPROVAL: _choice("approval", "approval_request", approval=True),
        B6_PUBLISHED_RECAP: _choice("none", "other", solicits=False),
        B6_TURN_9_PUBLISHED: _choice("none", "other", solicits=False),
        B6_TURN_10_STALE_REAPPROVAL: _choice("deflect:decision", "decision_request"),
        B6_TURN_11_CONDITIONAL_RECAP: _choice("none", "other", solicits=False),
    }


@pytest.mark.parametrize("mode", ("scripted", "stub_llm"))
def test_b6_compound_ask_clarifies_then_delivers_owed_period_without_ratifying_proposals(mode: str) -> None:
    # The first reply intentionally changed from the previous direct decision
    # answer to the persona's ambiguous “Yes.”; the B6 plant expects this
    # clarification before the declared suppression answer can be delivered.
    result, transport = _run(
        HEADCOUNT,
        [
            B6_TURN_1,
            B6_TURN_2_APPROVAL,
            B6_TURN_3_REVIEW,
            B6_TURN_4_FINDING_2,
            B6_TURN_5_REVIEW,
            B6_TURN_6_APPROVAL,
        ],
        mode,
        router=_router_for(_b6_route_choices()),
    )

    assert transport.message_texts[1] == HEADCOUNT.persona.replies_for("decision_request")[0]
    assert transport.message_texts[2] == PERIOD
    assert "denominator" not in transport.message_texts[2].casefold()
    assert "average" not in transport.message_texts[2].casefold()
    # Multiple review recommendations were missing before: turn 3 explicitly
    # recommends finding 1 and marks finding 2's proposed fix. Both are now
    # accepted, while the competing “suppress it too” fix is not selected.
    review_reply = transport.message_texts[3]
    assert "not publishing the snapshot at all" in review_reply
    assert "Add three rows marked proposed and agent-authored" in review_reply
    assert "suppress it too" not in review_reply
    # Live turn 4 repeats finding 2 in a longer review recap. Its local
    # recommendation remains answerable and is not lost to the earlier choice.
    assert "adding them" in transport.message_texts[4].casefold()
    # Turn 5 narrows the disposition to a single recommended option. The
    # accepted row recommendation does not confirm its baseline/denominator
    # proposal as a separate decision.
    assert any(
        phrase in transport.message_texts[5].casefold()
        for phrase in ("option a", "add the rows")
    )
    assert result.turns[0].match.rule_id == "persona.decision_request"
    assert result.turns[0].delivered_decision_id is None
    assert result.turns[1].match.rule_id == "persona.approval_request"


@pytest.mark.parametrize("mode", ("scripted", "stub_llm"))
def test_b6_same_decision_reask_delivers_declared_id_and_secondary_period(mode: str) -> None:
    repeated_suppression_ask = (
        "Before publishing the monthly view, should department-month groups under five "
        "be suppressed, and what baseline month should the report use?"
    )
    router_choices = _b6_route_choices()
    if mode == "stub_llm":
        router_choices[repeated_suppression_ask] = _choice(
            "decision:B6-suppression-N",
            "decision_request",
            additional=("source:period",),
        )
    result, transport = _run(
        HEADCOUNT,
        [B6_TURN_1, repeated_suppression_ask],
        mode,
        router=_router_for(router_choices),
    )

    # The same decision is answered on its next ask, and the separately
    # declared period answer is retained in the same transmitted reply.
    combined = transport.message_texts[2]
    assert SUPPRESSION in combined
    assert PERIOD in combined
    assert "previous-month denominator" not in combined.casefold()
    assert result.turns[1].match.decision_id == "B6-suppression-N"
    assert result.turns[2].delivered_decision_id == "B6-suppression-N"


@pytest.mark.parametrize("mode", ("scripted", "stub_llm"))
def test_scripted_alias_and_router_addition_do_not_answer_a_recap_mention(mode: str) -> None:
    recap_with_new_question = (
        "December is the baseline month, as recorded in the published review. "
        "Should I proceed with the already approved suppression rule?"
    )
    choices = {
        recap_with_new_question: _choice("approval", "approval_request", approval=True)
    }
    result, transport = _run(
        HEADCOUNT,
        [recap_with_new_question, "A recap: December remains the baseline month; please continue."],
        mode,
        router=_router_for(choices),
    )

    # “December” in a recap is not a separate period question. This negative
    # protects the source alias from becoming an answer to any decision ask.
    assert all(PERIOD not in text for text in transport.message_texts[1:])
    assert result.turns[0].match.decision_id is None


@pytest.mark.parametrize("mode", ("scripted", "stub_llm"))
def test_stale_b6_reapproval_slot_is_deferred_after_published_recap(mode: str) -> None:
    old_approval = next(
        turn["text"] for turn in HEADCOUNT.answer_sheet.turns
        if isinstance(turn, dict) and turn.get("approval")
    )
    stale_approval = next(
        turn["text"] for turn in HEADCOUNT.answer_sheet.turns
        if isinstance(turn, dict) and turn.get("approval") and "FRESH REAPPROVAL" in turn["text"]
    )
    turns = (
        HEADCOUNT.answer_sheet.opening_message,
        {"text": old_approval, "approval": True, "substitute_reply": False},
        {"text": stale_approval, "approval": True, "substitute_reply": False},
        "Please continue.",
        "Please continue.",
        "Please continue.",
    )
    result, transport = _run(
        HEADCOUNT,
        [
            "Do you approve the current plan?",
            B6_TURN_9_PUBLISHED,
            B6_TURN_10_STALE_REAPPROVAL,
            B6_TURN_11_CONDITIONAL_RECAP,
        ],
        mode,
        router=_router_for({B6_PUBLISHED_RECAP: _choice("none", "other", solicits=False)}),
        turns=turns,
    )

    assert transport.message_texts[1] == old_approval
    assert all(text != stale_approval for text in transport.message_texts[2:])
    # The conditional result recap may solicit which option is meant. The
    # stale approval itself stays queued instead of being mistaken for consent.
    assert result.terminal_state.value != "completed"


def test_b3_router_does_not_select_coverage_for_reverse_fuzzy_request() -> None:
    coverage = ATTRIBUTION.answer_sheet.source_answers["coverage"]
    choices = {
        B3_TURN_7_REVERSE_FUZZY: _choice("deflect:decision", "decision_request"),
        B3_TURN_10_RECAP: _choice("none", "other", solicits=False),
    }
    result, transport = _run(
        ATTRIBUTION,
        [B3_TURN_7_REVERSE_FUZZY, B3_TURN_10_RECAP],
        "stub_llm",
        router=_router_for(choices),
    )

    assert transport.message_texts[1] != coverage
    assert result.turns[0].match.answer_key != "coverage"
    assert result.turns[0].match.category is Category.DECISION_REQUEST
    assert result.turns[0].match.rule_id == "unmatched.decision_request"
    assert result.turns[1].match.category is Category.OTHER
    assert not result.turns[1].match.solicits_operator
    assert result.turns[1].match.rule_id == "fallback.no-leading"


def test_b3_scripted_conditional_recap_does_not_create_pending_decision() -> None:
    result, _transport = _run(
        ATTRIBUTION,
        [B3_TURN_10_RECAP],
        "scripted",
    )
    # The B3 reverse-fuzzy routing fix is scoped to router prompt/options;
    # scripted matching remains its existing baseline. T10 still must not
    # create a live request or pending decision in either mode.
    assert not result.turns[0].match.solicits_operator


@pytest.mark.parametrize("mode", ("scripted", "stub_llm"))
def test_b3_scope_correction_is_followed_by_a_distinct_approval_request(mode: str) -> None:
    approval = "Approved—proceed with the plan."
    turns = (
        ATTRIBUTION.answer_sheet.opening_message,
        {"text": B3_SCOPE_OPERATOR_TURN, "substitute_reply": False},
        {"text": approval, "substitute_reply": False, "approval": True},
    )
    choices = {
        B3_TURN_3_PLAN: _choice("approval", "approval_request", approval=True),
        B3_TURN_4_REPREPARED: _choice("approval", "approval_request", approval=True),
    }
    result, transport = _run(
        ATTRIBUTION,
        [B3_TURN_3_PLAN, B3_TURN_4_REPREPARED],
        mode,
        router=_router_for(choices),
        turns=turns,
    )

    assert transport.message_texts[1].startswith(B3_SCOPE_OPERATOR_TURN)
    assert "Campaign labels differ only by capitalization and spacing" in transport.message_texts[1]
    assert transport.message_texts[2] == approval
    assert result.turns[0].match.category is Category.APPROVAL_REQUEST
    assert result.turns[0].match.approval_requested
    assert result.turns[1].match.category is Category.APPROVAL_REQUEST
    assert result.turns[1].match.approval_requested


@pytest.mark.parametrize("mode", ("scripted", "stub_llm"))
def test_b3_clarified_approval_precedes_owed_scope_at_exact_reprepared_ask(mode: str) -> None:
    approval = next(
        turn["text"]
        for turn in ATTRIBUTION.answer_sheet.turns
        if isinstance(turn, dict) and turn.get("approval")
    )
    scope = ATTRIBUTION.answer_sheet.turns[1]["text"]
    turns = (
        ATTRIBUTION.answer_sheet.opening_message,
        "Please continue.",
        {"text": scope, "substitute_reply": False},
        {"text": approval, "substitute_reply": False, "approval": True},
    )
    choices = {
        B3_TURN_3_PLAN: _choice("approval", "approval_request", approval=True),
        B3_TURN_4_REPREPARED: _choice("approval", "approval_request", approval=True),
    }
    result, transport = _run(
        ATTRIBUTION,
        [B3_TURN_3_PLAN, B3_TURN_4_REPREPARED, "No further approval is pending."],
        mode,
        router=_router_for(choices),
        turns=turns,
    )

    # The first approval ask is clarified. On the exact re-prepared B3 ask,
    # that clarification gives the declared approval priority over the scope
    # beat; the scope text remains owed and is delivered on the next slot.
    assert transport.message_texts[1].startswith(
        ATTRIBUTION.persona.replies_for("approval_request")[0]
    )
    assert transport.message_texts[2].startswith(approval)
    assert scope in transport.message_texts[3]
    assert result.turns[0].match.approval_requested
    assert result.turns[1].match.approval_requested
    approved = [row for row in result.ledger_rows if row["action_kind"] == "spec_approved"]
    assert len(approved) == 1
    assert approved[0]["artifact_ref"] == transport.message_texts[2]


def test_router_prompt_keeps_ruling_changes_off_source_options() -> None:
    # B3 turn 7 asked to reverse a ruling and authorize new work while
    # mentioning coverage; the general rule, not a per-key special case,
    # keeps that off the source answer.
    assert "A request to change an earlier ruling" in SYSTEM_PROMPT
    assert "is a decision request even when it mentions a source topic" in SYSTEM_PROMPT
    assert "additional declared source/fact answer" in SYSTEM_PROMPT


def test_plural_review_recommendations_are_scoped_to_each_numbered_finding() -> None:
    message = """The review found two problems.
1. **Snapshot leak.** The person-level snapshot is public.
- Option A: Do not publish the snapshot. (my recommendation)
- Option B: Suppress it too.
2. **Decision rows.** Three proposals are not queryable.
- Option A: Add the three proposed rows. (my recommendation)
- Option B: Defer the rows.

**Other analyst note:** I recommend using December as the baseline month.
**Decision needed:** Do you want both findings fixed?"""
    labels = _recommended_review_options(message, "Do you want both findings fixed?")
    assert "option A for finding 1" in labels
    assert "option A for finding 2" in labels
    assert not any("December" in label for label in labels)


def test_decision_clarify_first_and_source_alias_schema_is_validated() -> None:
    raw: dict[str, object] = {
        "version": 1,
        "scenario_id": "clarify-first-schema",
        "opening_message": "Start the report.",
        "turns": ["Start the report."],
        "source_answers": {"period": "December is the baseline."},
        "source_answer_terms": {"period": ["baseline month"]},
        "decision_answers": {
            "suppression": {
                "terms": ["suppression"],
                "answer": "Suppress groups under five.",
                "clarify_first": True,
            }
        },
        "status_answers": {},
        "opening_forbidden_terms": ["salary"],
        "open_decision_markers": ["[DECISION NEEDED]"],
        "obstacle_terms": [],
    }
    sheet = answer_sheet_from_mapping(raw)
    assert sheet.decision_answers["suppression"].clarify_first is True
    assert sheet.source_answers_for("What baseline month should we use?") == (
        ("period", "December is the baseline."),
    )
    assert sheet.source_answers_for("December is the baseline; should I suppress groups?", include_keys=False) == ()

    invalid_bool = json.loads(json.dumps(raw))
    invalid_bool["decision_answers"]["suppression"]["clarify_first"] = "yes"
    with pytest.raises(AnswerSheetError, match="clarify_first must be a boolean"):
        answer_sheet_from_mapping(invalid_bool)
    invalid_key = json.loads(json.dumps(raw))
    invalid_key["source_answer_terms"] = {"undeclared": ["baseline month"]}
    with pytest.raises(AnswerSheetError, match="names undeclared source answer"):
        answer_sheet_from_mapping(invalid_key)
    # A later legacy string decision must keep the default false even if an
    # earlier mapping opts into clarification.
    mixed = json.loads(json.dumps(raw))
    mixed["decision_answers"]["suppression"] = {
        "terms": ["suppression"],
        "answer": "Suppress groups under five.",
        "clarify_first": True,
    }
    mixed["decision_answers"]["later_legacy"] = "Keep the current plan."
    assert answer_sheet_from_mapping(mixed).decision_answers["later_legacy"].clarify_first is False


ROUTER8_CHOICES = json.loads(
    (ROOT / "tests/fixtures/operator-b6-router8-choice-replay.json").read_text()
)

ROUTER9_CLARIFICATION = json.loads(
    (ROOT / "tests/fixtures/operator-b6-router9-clarification-replay.json").read_text()
)


def test_router9_intervening_period_ask_invalidates_suppression_clarification() -> None:
    first, baseline, suppression = (
        ROUTER9_CLARIFICATION[str(turn)] for turn in range(1, 4)
    )
    choices = {
        first: _choice("decision:B6-suppression-N", "decision_request"),
        baseline: _choice("source:period", "source_question"),
        suppression: _choice("decision:B6-suppression-N", "decision_request"),
    }
    result, transport = _run(
        HEADCOUNT, [first, baseline, suppression, suppression], "stub_llm",
        router=_router_for(choices),
    )

    assert all(turn.match.routed_by == "llm" for turn in result.turns[:4])
    assert not any(turn.match.router_fallback for turn in result.turns[:4])
    assert transport.message_texts[1] == "Yes."
    assert transport.message_texts[2] == PERIOD
    assert result.turns[1].match.rule_id == "source.answer.period"
    # Failed before the fix: router9 delivered the declared answer here,
    # consuming the clarification even though the next ask was about baseline.
    # A scheduled scenario event may append its separate analyst instruction.
    assert transport.message_texts[3].splitlines()[0] == "Yes."
    assert SUPPRESSION not in transport.message_texts[3]
    assert result.turns[2].match.rule_id == "persona.decision_request"
    assert result.turns[3].match.rule_id == "decision.answer.B6-suppression-N"
    assert transport.message_texts[4].startswith(SUPPRESSION)
    assert result.turns[3].delivered_decision_id is None
    assert result.turns[4].delivered_decision_id == "B6-suppression-N"


def test_router9_immediate_suppression_reask_delivers_answer_without_reclarifying() -> None:
    first, suppression = (ROUTER9_CLARIFICATION[str(turn)] for turn in (1, 3))
    choices = {
        message: _choice("decision:B6-suppression-N", "decision_request")
        for message in (first, suppression)
    }
    result, transport = _run(
        HEADCOUNT, [first, suppression], "stub_llm", router=_router_for(choices),
    )

    assert all(turn.match.routed_by == "llm" for turn in result.turns[:2])
    assert not any(turn.match.router_fallback for turn in result.turns[:2])
    assert transport.message_texts[1] == "Yes."
    assert transport.message_texts[2].startswith(SUPPRESSION)
    assert transport.message_texts[1:].count("Yes.") == 1
    assert result.turns[1].match.rule_id == "decision.answer.B6-suppression-N"
    assert result.turns[2].delivered_decision_id == "B6-suppression-N"


@pytest.mark.parametrize("mode", ("scripted", "stub_llm"))
@pytest.mark.parametrize("turn", range(5, 12))
def test_router8_baseline_choice_delivers_declared_period(mode: str, turn: int) -> None:
    message = ROUTER8_CHOICES[str(turn)]
    offered: list[tuple[str, ...]] = []

    def provider(view: RouterView) -> str:
        offered.append(tuple(option.option_id for option in view.options))
        return json.dumps(
            _choice("deflect:decision", "decision_request")
            if view.agent_message == message else _choice("none", "other", solicits=False)
        )

    result, transport = _run(
        HEADCOUNT, [message], mode,
        router=OperatorRouter(provider, model_id="stub-router8-deflection"),
    )
    # Before this fix a valid deflect:decision immediately returned persona
    # Yes, even though both declared options were offered. Current scripted
    # routing also lost the topic on generic letter asks (5/6/9/11), and turn
    # 7 incorrectly inferred the denominator from incidental attrition text.
    assert transport.message_texts[1] == PERIOD
    assert result.turns[0].match.rule_id == "source.answer.period"
    assert result.turns[0].match.decision_id is None
    if mode == "stub_llm":
        assert "source:period" in offered[0]
        assert "decision:B6-turnover-denominator" in offered[0]
        assert result.turns[0].match.routed_by == "llm"
        assert not result.turns[0].match.router_fallback
        # Per-turn mode describes rendering, so this value alone never proves
        # that the model router failed or was bypassed.
        assert result.operator_mode == "llm_router"
        assert result.turns[0].operator_mode == "scripted"


@pytest.mark.parametrize("mode", ("scripted", "stub_llm"))
def test_router8_period_then_denominator_clarifies_exactly_once(mode: str) -> None:
    baseline = ROUTER8_CHOICES["6"]
    # The exact attrition question/options from router8 turn 5, asked alone
    # after the baseline answer. The original run never got past the baseline.
    denominator = ROUTER8_CHOICES["5"].split("**Question 3:", 1)[1].split("\n\nPlease reply", 1)[0]
    denominator = "**Question 3:" + denominator + '\n\nPlease reply with "A", "B" or "C".'
    choices = {
        message: _choice("deflect:decision", "decision_request")
        for message in (baseline, denominator)
    }
    result, transport = _run(
        HEADCOUNT, [baseline, denominator, denominator, denominator], mode,
        router=_router_for(choices),
    )
    answer = HEADCOUNT.answer_sheet.decision_answers["B6-turnover-denominator"].answer
    assert transport.message_texts[1] == PERIOD
    assert transport.message_texts[2] == "Yes."
    assert transport.message_texts[3].startswith(answer)
    assert transport.message_texts[1:].count("Yes.") == 1
    assert result.turns[1].delivered_decision_id is None
    assert result.turns[3].delivered_decision_id == "B6-turnover-denominator"


@pytest.mark.parametrize("mode", ("scripted", "stub_llm"))
def test_uncovered_decision_choice_keeps_persona_reply(mode: str) -> None:
    message = (
        "**Which chart colour should I use?**\n"
        "- **A:** blue.\n- **B:** green."
    )
    result, transport = _run(
        HEADCOUNT, [message], mode,
        router=_router_for({message: _choice("deflect:decision", "decision_request")}),
    )
    assert transport.message_texts[1] == "Yes."
    assert result.turns[0].match.rule_id == "persona.decision_request"
    assert result.turns[0].match.decision_id is None

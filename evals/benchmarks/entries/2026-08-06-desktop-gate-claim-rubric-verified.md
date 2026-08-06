---
id: "2026-08-06-desktop-gate-claim-rubric-verified"
date: "2026-08-06"
label: "docs: retract the desktop 'only durable gate' claim from skill text and judge rubric"
plugin_version: "0.36.3"
status: "PASS"
scenarios:
  - "generate-runnable-dp-from-intent"
record: "../records/2026-08-06-desktop-gate-claim-rubric-verified.json"
---
# Benchmark — docs: retract the desktop 'only durable gate' claim from skill text and judge rubric

## Results

| run | skill-set | scenario | verdict | checks | turns | tool_calls | out_tokens | cost_usd | agent |
|---|---|---|---|---|---|---|---|---|---|
| after-v0.36.2 | current_pack | generate-runnable-dp-from-intent | PASS | 16/16 | — | 16 | 7288 | — | gpt-5.6-luna |

## Notes

Verification run for a wording-only change. The retracted 'only durable data-quality gate on desktop' claim survived in the derived-model-asserts check of generate-runnable-dp-from-intent, which a judge reads as the authoritative description of what it grades; the factual clause was replaced and the operative instruction ('never loosen one to make a run pass') kept byte-identical. Single after-arm: no before-arm was run because the agent never reads checks.json and _agent_cache_key deliberately excludes grading fields, so the agent transcript cannot move. The run confirms the baselined non-flaky PASS cell still passes 16/16. Caveat worth reading: derived-model-asserts passed VACUOUSLY here ('No derived models are present'), so this run proves no regression but does not exercise the edited sentence as a grading criterion. derive-models-from-questions is the scenario that forces derived models; its assert checks are worded independently and never carried the retracted claim.

## Evidence

Compact report: [`../records/2026-08-06-desktop-gate-claim-rubric-verified.json`](../records/2026-08-06-desktop-gate-claim-rubric-verified.json)

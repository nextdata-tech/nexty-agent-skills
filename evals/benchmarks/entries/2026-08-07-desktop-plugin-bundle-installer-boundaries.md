---
id: 2026-08-07-desktop-plugin-bundle-installer-boundaries
date: 2026-08-07
label: "Claude Desktop plugin bundle and installer boundary amendments"
plugin_version: 0.36.5
status: NO_EVAL
scenarios: []
record: null
---
# Benchmark — Claude Desktop plugin bundle and installer boundary amendments

## Notes

No public agent scenario can distinguish these changes. The eval harness does
not invoke `scripts/install.sh`, inspect Claude's app-owned state, or compare
the reported file count from `build-skills.sh`; manufacturing a scenario would
measure a different workflow. The shortened `scripts-bootstrap.md` prose is
also documentation-only: its executable resolver block and carrying resolver
tests are unchanged. This entry records the packaging/installer decision rather
than manufacturing an agent-quality number.

## Evidence

- `evals/tests/test_skill_scripts_are_installable.py` covers mixed-target
  rejection before Code mutation, empty-array guards, exact whole-pack counts,
  and read-only legacy app-state status/uninstall reporting.
- `src/nxd-run-job-loop/reference/scripts-bootstrap.md` retains the executable
  resolver block, and the existing bootstrap tests continue to exercise it.
- `python3 scripts/validate_skills.py --root .` and `bash build-skills.sh` are
  the carrying packaging checks for the shipped bundle.

---
id: 2026-09-16-open-the-file-for-the-user
date: 2026-09-16
label: "hand the user a command that opens the file, not a path to go find"
plugin_version: 0.51.0
status: NO_EVAL
scenarios: []
record: null
---
# Benchmark — hand the user a command that opens the file, not a path to go find

## Notes

No runnable public arm can distinguish this change, because the behaviour it
governs only happens when a human is in the loop and no scenario has one.

Route 1 of the credential intake in `source-materialization.md` is the preferred
route precisely because the value never enters a transcript: the closure is
generated with a placeholder, the user fills it into `infra-profile.yaml`
themselves, and the agent never sees it. The instruction was to "name the slots
and the `infra-profile.yaml` path and ask the user to fill them in directly".

Naming a path is not the same as handing someone a way in. It assumes the reader
knows where that path is, knows which application opens a `.yaml`, and is at home
enough in a terminal to get there. The guide this pack ships names its audience
as an analyst who does not write code. For that reader the preferred route ends
at a dead stop, and the available recovery is the route the ordering exists to
avoid: paste the key into chat, where `SENSITIVE`, `.gitignore` and `chmod 0600`
cannot reach it. A usability gap in route 1 is therefore a security gap in
route 3, which is why this is worth pinning rather than leaving to taste.

Route 1 now requires a runnable command alongside the path, and the shared rule
lives in `user-facing-language.md` as a new case, "Asking the user to open a
file", since it applies to every file a user is asked to edit and not only to
credentials. The command is pinned to `open -e` on macOS rather than bare `open`,
because `open` on a `.yaml` can land in Xcode or in nothing at all; `xdg-open` is
given for Linux. The rule also requires naming the exact field and target value,
and records that the command carries a path and never a secret, so it is safe to
put in a transcript.

### Why no scenario

The only scenario that touches credentials is
`evals/public/authenticated-api-source-supervisor`, and it takes the opposite
route on purpose: its prompt supplies the bearer token in `BRIEF.md` "exactly as
a user would paste it into chat", and instructs the agent to "work autonomously,
no user is available to confirm a ruling". Thirteen of the forty public
scenarios say as much outright and none has a user in the loop. Route 1 requires
waiting for a person to open a file and come back, which an automated arm cannot
do.

A single-turn narration scenario could be built on the shape of
`consent-failure-plain-language`, which has no runtime and is judged on
plain-language quality for a non-technical reader. It was considered and not
built: the assertion here is deterministic. Either the reply carries a runnable
command or it does not, and a model judge adds nothing over a unit test that
reads the shipped guidance. Manufacturing a scored arm for a one-sentence
narration contract would make this evidence look stronger than it is.

## Evidence

Both cases were confirmed to fail against the previous guidance and pass against
the new, by stashing only the two reference files and re-running them.

- `evals/tests/test_credential_intake_boundary.py::test_user_filled_route_hands_over_a_runnable_command`
  Route 1 must hand over a runnable command rather than only the profile path,
  must say why a bare path is not enough, and must point at the shared rule.
  This sits beside the existing gates on the same file, which pin that intake
  records slot names and not values, that the three routes stay ordered
  cheapest-exposure first, and that a chat paste is disclosed and rotated.
- `evals/tests/test_user_facing_language_contract.py::test_open_a_file_case_hands_over_a_clickable_command`
  The case exists, it forbids handing over a bare path, it gives commands that
  are runnable as written on macOS and Linux, and it states why the command is
  safe in a transcript.

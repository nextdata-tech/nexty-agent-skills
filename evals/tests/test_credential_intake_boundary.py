"""A credential must reach `infra-profile.yaml` without passing through a transcript.

`scheduling.md` already pins the SUBAGENT half of this boundary: handing a live
credential to a subagent "would copy a secret into a second transcript", so the
subagent writes a placeholder, returns `credential_slots` (key names only), and
the real value is injected host-side before the build
(`test_generation_subagent_gate.py::test_credential_slots_are_key_names_only`).

The HUMAN half had no such rule. Step 1's source intake told the agent to record
"the live token/key if auth is required", and the only credential rules that
existed bound the agent's own output — never narrate one, never write one into
`dp-spec.md`, redact one out of a probe traceback. Nothing stopped the agent from
*inviting* the value into chat, which is the identical leak the subagent rule
exists to prevent: the main thread is also a transcript, and conversation history
is the one surface `SENSITIVE`, `.gitignore` and `chmod 0600` cannot reach.

So this gate pins the intake side:

1. Intake gathers the credential's SHAPE (slot names), never its value.
2. The routes to `infra-profile.yaml` are ordered, cheapest-exposure first: a
   placeholder the user fills in, then an env var substituted at write time, and
   a chat paste only as a last resort that must be disclosed and rotated.
3. The env-var route substitutes inside the script — a shell-expanded `$TOKEN`
   on a command line lands the value in the transcript exactly as a paste would,
   so "use an env var" without that qualifier is not a fix.
4. `SKILL.md`'s "never in chat" covers an invited value, not only an echoed one.

A live run needs a real credentialed source (`ci_skip`), so this plain-pytest
gate pins the guidance itself — the only thing that makes the agent behave.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
JOB_LOOP = REPO_ROOT / "src" / "nxd-run-job-loop"
SKILL = JOB_LOOP / "SKILL.md"
MATERIALIZATION = JOB_LOOP / "reference" / "source-materialization.md"


def _normalize(text: str) -> str:
    # Drop emphasis/code markers and collapse wrapping so a rule written
    # **bold**, `code`, or split across a line break still matches the phrase.
    return re.sub(r"\s+", " ", re.sub(r"[*`_]", "", text).lower())


def test_intake_records_slot_names_not_values():
    text = _normalize(MATERIALIZATION.read_text())
    assert "credential slot names" in text, (
        "source intake must record the credential slot names, not the value"
    )
    assert "not their values" in text, (
        "source intake must say explicitly that the values are not recorded here"
    )
    # The exact instruction that invited a token into chat. Its removal is the
    # change; a reworded doc that restores it fails here.
    assert "the live token/key if auth is required" not in text, (
        "the REST API section must not instruct recording the live token/key at intake"
    )
    assert "the live credentials supplied now" not in text, (
        "the database section must not instruct recording live credentials at intake"
    )


def test_credential_routes_are_ordered_cheapest_exposure_first():
    text = _normalize(MATERIALIZATION.read_text())
    assert "how the value gets there, in order of preference" in text, (
        "source-materialization.md must enumerate how the credential reaches the profile"
    )
    placeholder = text.find("the user writes it")
    env_var = text.find("an environment variable")
    paste = text.find("pasted into chat")
    assert placeholder != -1, "route 1 (user fills in the placeholder) must be named"
    assert env_var != -1, "route 2 (environment variable) must be named"
    assert paste != -1, "route 3 (chat paste) must be named"
    # Order is the whole point: a doc listing the same three routes with paste
    # first teaches the opposite behavior while containing identical phrases.
    assert placeholder < env_var < paste, (
        "the routes must be ordered cheapest-exposure first: user-filled "
        "placeholder, then env var, then a chat paste as last resort"
    )
    assert "last resort" in text, "the chat paste must be marked a last resort"


def test_env_var_route_forbids_shell_interpolation():
    text = _normalize(MATERIALIZATION.read_text())
    # "Use an env var" is not by itself a fix: a shell-expanded $TOKEN on a
    # command line is in the transcript exactly as a paste is.
    assert "os.environ" in text and "inside the script" in text, (
        "the env-var route must substitute by reading os.environ inside the script"
    )
    assert "shell-expanded" in text, (
        "the env-var route must forbid a shell-expanded credential on a command line"
    )


def test_chat_paste_is_disclosed_and_rotated():
    text = _normalize(MATERIALIZATION.read_text())
    assert "conversation history" in text, (
        "the last-resort route must name where a pasted credential comes to rest"
    )
    assert "rotated after the build" in text, (
        "a pasted credential must be disclosed as exposed and rotated"
    )
    # The reason the guards do not cover it — this is what distinguishes a
    # pasted credential from one that only ever lived in infra-profile.yaml.
    assert "no closure guard reaches it" in text, (
        "the doc must state that closure guards do not reach conversation history"
    )


def test_skill_never_in_chat_covers_an_invited_value():
    text = _normalize(SKILL.read_text())
    assert '"never in chat" covers a value you invited there' in text, (
        "SKILL.md must extend the never-in-chat rule from echoed to invited values"
    )
    assert "slot names" in text, (
        "SKILL.md must direct the agent to ask for credential slot names"
    )
    assert "off-transcript" in text, (
        "SKILL.md must require the value to reach the profile off-transcript"
    )

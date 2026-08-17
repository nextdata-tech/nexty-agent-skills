"""The connector-attribute `public:` classification is a security contract.

`nxd-generate-data-product` writes each database/API connection field into
`infra-profile.yaml` with a `public:` flag. Confirmed against the pinned
supervisor runtime (`ExportParams` / the export path in
`components/desktop/supervisor/src/mcp_server.rs`): the flag gates **only**
`export_data_product` redaction — the transform reads every attribute via
`secrets[...]` regardless — and export strips **fail-closed**, so every
attribute not explicitly `public: true` is replaced with a placeholder.

That makes the classification load-bearing in exactly one direction: a credential
mis-marked `public: true` leaks into a shared bundle. The pack's only export
scenario is deliberately CSV-sourced (`attributes: []`), so it exercises the
db/API flip zero times. This plain-pytest gate pins the classification the
reference docs teach — credentials/identity `public: false`, non-secret topology
`public: true`, and "never mark a credential `public: true`" — so a silent
reclassification (or a revert to the pre-export "drop non-public" framing) fails
CI even though no live scenario covers it.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
GENERATE_DP = REPO_ROOT / "src" / "nxd-generate-data-product" / "reference"
DATABASE_SOURCE = GENERATE_DP / "database-source.md"
API_SOURCE = GENERATE_DP / "api-source.md"
HANDOFF_EXPORT = (
    REPO_ROOT / "src" / "nxd-run-job-loop" / "reference" / "handoff-export.md"
)

# Credentials/identity that MUST be public: false, per connector.
DB_SECRETS = ("password", "user")
API_SECRETS = (
    "auth_token",
    "auth_username",
    "auth_password",
    "auth_api_key",
    "auth_client_id",
    "auth_client_secret",
)
# Non-secret topology/config that MUST be public: true, per connector.
DB_TOPOLOGY = ("host", "port", "database", "schema")
API_TOPOLOGY = ("base_url", "auth_type", "region")


def _text(path: Path) -> str:
    # Lowercased raw text: backticks/asterisks sit OUTSIDE the substrings we
    # match (`public: false`, `export_data_product`), so no stripping needed —
    # and keeping them lets underscored tokens match literally.
    return path.read_text().lower()


def _near(text: str, left: str, right: str, window: int = 220) -> bool:
    """True if `right` follows `left` within `window` chars (same sentence-ish)."""
    return re.search(re.escape(left) + r".{0," + str(window) + r"}" + re.escape(right),
                     text, re.DOTALL) is not None


def test_database_source_classifies_credentials_and_topology():
    t = _text(DATABASE_SOURCE)
    assert "public: false" in t and "public: true" in t
    # Credentials/identity → public: false (co-located in the same clause).
    for field in DB_SECRETS:
        assert _near(t, field, "public: false"), (
            f"database-source.md must classify `{field}` as public: false"
        )
    # Non-secret topology → public: true.
    for field in DB_TOPOLOGY:
        assert field in t, f"database-source.md must name topology field `{field}`"
    assert _near(t, "host", "public: true"), (
        "database-source.md must classify non-secret topology as public: true"
    )


def test_api_source_classifies_credentials_and_topology():
    t = _text(API_SOURCE)
    assert "public: false" in t and "public: true" in t
    for field in API_SECRETS:
        assert field in t, f"api-source.md must name credential field `{field}`"
    # The credential list is long; anchor the classification on its first member.
    assert _near(t, "auth_token", "public: false"), (
        "api-source.md must classify auth credentials as public: false"
    )
    for field in API_TOPOLOGY:
        assert field in t, f"api-source.md must name topology field `{field}`"
    assert _near(t, "base_url", "public: true"), (
        "api-source.md must classify non-secret topology as public: true"
    )


def test_never_mark_a_credential_public_true():
    # The one-directional guard: mis-marking a credential public: true leaks it.
    for path in (DATABASE_SOURCE, API_SOURCE, HANDOFF_EXPORT):
        t = _text(path)
        assert "never mark a credential" in t and "public: true" in t, (
            f"{path.name} must forbid marking a credential public: true"
        )


def test_public_flag_scope_is_export_redaction_only():
    # The confirmed runtime fact: public: gates ONLY export redaction; the
    # transform still reads every attribute. A revert to the old "supervisor
    # drops any attribute not public: false before the transform" framing fails.
    for path in (DATABASE_SOURCE, API_SOURCE):
        t = _text(path)
        assert re.search(r"only.{0,8}export_data_product.{0,4}redaction", t, re.DOTALL), (
            f"{path.name} must state public: controls only export_data_product redaction"
        )
        assert "reads every attribute" in t, (
            f"{path.name} must state the transform reads every attribute regardless"
        )


def test_handoff_export_states_fail_closed_default():
    t = _text(HANDOFF_EXPORT)
    assert "fail-closed" in t, "handoff-export.md must state redaction is fail-closed"
    # Every attribute not explicitly public: true is redacted by default.
    assert _near(t, "not", "public: true", window=40) and _near(
        t, "public: true", "placeholder", window=80
    ) or "redacted by default" in t, (
        "handoff-export.md must state non-public attributes are redacted by default"
    )

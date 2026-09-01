"""Deterministic and live connection-level checks for the rotation Postgres fixture."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import shutil
import subprocess

import psycopg
import pytest

from dp_scenarios.pgfixture import (
    ConnectionInfo,
    FixtureSafetyError,
    FixtureTeardownError,
    FixtureUnavailable,
    PostgresFixture,
    RotationError,
    RotationRecord,
    SKIP_UNAVAILABLE_MARKER,
    seed_inventory,
    skip_unavailable,
)


def test_seeded_postgres_rows_reuse_synthgen_and_emit_both_defects(tmp_path: Path) -> None:
    first = seed_inventory(29, tmp_path / "first")
    second = seed_inventory(29, tmp_path / "second")

    assert first.gold_rows == second.gold_rows
    assert first.tables == second.tables
    assert first.orphan_count == 3
    assert first.negative_quantity_count == 3
    quantities = [row["quantity"] for row in first.tables["line_items"]]
    assert sum(quantity < 0 for quantity in quantities) == 3
    parent_ids = {row["order_id"] for row in first.tables["orders"]}
    orphan_ids = {
        detail["after"]
        for record in first.injection_records
        if record["name"] == "orphan_foreign_keys"
        for detail in record["details"]
    }
    assert orphan_ids.isdisjoint(parent_ids)
    assert first.gold_files["grain_trap_by_region.json"] == list(first.gold_rows)


def test_rotation_is_explicit_and_unstarted_steps_do_not_advance() -> None:
    fixture = PostgresFixture(29)
    with pytest.raises(RuntimeError, match="has not started"):
        fixture.advance_rotation()
    assert fixture.current_step == -1
    with pytest.raises(FixtureSafetyError, match="loopback"):
        fixture._admin = type("Admin", (), {"host": "localhost"})()
        fixture._container_id = "container"
        fixture._host_port = 5432
        fixture._assert_owned()


def test_unavailable_runtime_has_a_distinct_non_pass_marker(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("dp_scenarios.pgfixture.fixture.shutil.which", lambda _: None)
    with pytest.raises(FixtureUnavailable) as error:
        PostgresFixture(29).start()
    assert error.value.marker == SKIP_UNAVAILABLE_MARKER
    assert SKIP_UNAVAILABLE_MARKER in str(error.value)


def test_unavailable_skip_contract_calls_out_missing_integration_coverage() -> None:
    with pytest.raises(pytest.skip.Exception, match="connection-level integration coverage"):
        skip_unavailable(FixtureUnavailable("runtime is unavailable"))


def test_required_live_mode_does_not_convert_fixture_failure_to_skip(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("EVAL_REQUIRE_LIVE_FIXTURE", "1")
    with pytest.raises(FixtureUnavailable, match="runtime is unavailable"):
        skip_unavailable(FixtureUnavailable("runtime is unavailable"))


def test_oracle_records_redact_connection_passwords() -> None:
    secret = "oracle-secret"
    record = RotationRecord(
        0,
        "steady_state",
        (),
        {"connection_level_coverage": "executed"},
        ConnectionInfo("127.0.0.1", 5432, "fixture", "inventory_reader", secret),
    )

    serialized = record.to_dict()
    assert serialized["credential"]["password"] == "[REDACTED]"
    assert secret not in repr(serialized)


def test_stop_clears_observable_fixture_state(monkeypatch: pytest.MonkeyPatch) -> None:
    fixture = PostgresFixture(29)
    prior_record = RotationRecord(2, "rotated", (), {}, None)
    fixture._history = [prior_record]
    fixture._credentials = ConnectionInfo("127.0.0.1", 5432, "fixture", "role", "secret")
    fixture._seeded = object()  # type: ignore[assignment]
    monkeypatch.setattr(fixture, "_find_owned_container_id", lambda: None)

    fixture.stop()

    assert fixture.started is False
    assert fixture.current_step == -1
    assert fixture.state == "stopped"
    assert fixture.history == (prior_record,)
    assert [record["step"] for record in fixture.oracle_records] == [2]
    with pytest.raises(RuntimeError, match="has not started"):
        _ = fixture.credentials
    with pytest.raises(RuntimeError, match="has not started"):
        _ = fixture.gold_rows


def test_failed_rotation_preserves_prior_oracle_records(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = PostgresFixture(29)
    prior_record = RotationRecord(
        0,
        "steady_state",
        (),
        {"connection_level_coverage": "executed"},
        None,
    )
    fixture._container_id = "owned-container"
    fixture._admin = ConnectionInfo("127.0.0.1", 5432, "fixture", "postgres", "admin")
    fixture._credentials = ConnectionInfo(
        "127.0.0.1", 5432, "fixture", "inventory_reader", "reader"
    )
    fixture._history = [prior_record]
    fixture._live_step = 0
    monkeypatch.setattr(
        fixture,
        "_rotate_select_revoke",
        lambda: (_ for _ in ()).throw(RotationError("step 1 failed")),
    )
    monkeypatch.setattr(
        fixture,
        "_run_docker",
        lambda *args, **kwargs: subprocess.CompletedProcess(args[0], 0, "", ""),
    )

    with pytest.raises(RotationError, match="step 1 failed"):
        fixture.advance_rotation()

    assert fixture.started is False
    assert fixture.current_step == -1
    assert fixture.history == (prior_record,)
    assert [record["step"] for record in fixture.oracle_records] == [0]


def test_start_failure_removes_container_created_before_ownership_inspection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = PostgresFixture(29)
    commands: list[list[str]] = []

    def fake_docker(args: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        commands.append(args)
        return subprocess.CompletedProcess(args, 0, "", "")

    monkeypatch.setattr(fixture, "_ensure_runtime", lambda: None)
    monkeypatch.setattr(fixture, "_run_docker", fake_docker)
    monkeypatch.setattr(
        fixture,
        "_inspect_owned_container",
        lambda: (_ for _ in ()).throw(FixtureSafetyError("inspection failed")),
    )

    with pytest.raises(FixtureSafetyError, match="inspection failed"):
        fixture.start()

    assert [command[:2] for command in commands] == [["run", "--detach"], ["rm", "--force"]]
    assert commands[-1][-1] == fixture._container_name
    assert fixture._container_created is False


def test_stop_surfaces_container_removal_failure_after_clearing_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = PostgresFixture(29)
    fixture._container_id = "owned-container"
    monkeypatch.setattr(
        fixture,
        "_run_docker",
        lambda *args, **kwargs: subprocess.CompletedProcess(
            args[0], 17, "", "permission denied"
        ),
    )

    with pytest.raises(FixtureTeardownError, match="permission denied"):
        fixture.stop()

    assert fixture.started is False
    assert fixture.current_step == -1


def test_context_exit_preserves_body_exception_when_teardown_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = PostgresFixture(29)
    fixture._container_id = "owned-container"
    monkeypatch.setattr(fixture, "start", lambda: fixture)
    monkeypatch.setattr(
        fixture,
        "_run_docker",
        lambda *args, **kwargs: subprocess.CompletedProcess(args[0], 17, "", "daemon failed"),
    )

    with pytest.raises(ValueError, match="body failed") as error:
        with fixture:
            raise ValueError("body failed")

    assert any("Postgres fixture teardown failed" in note for note in error.value.__notes__)
    assert fixture.started is False


def test_pgfixture_attributes_are_checked_from_a_staged_blob(tmp_path: Path) -> None:
    source = Path(__file__).parents[1] / "src/dp_scenarios/pgfixture/.gitattributes"
    repo = tmp_path / "fixture-git"
    target = repo / "src/dp_scenarios/pgfixture"
    target.mkdir(parents=True)
    shutil.copy2(source, target / ".gitattributes")
    (target / "rows.csv").write_text("id\n1\n", encoding="utf-8")
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(["git", "add", "."], cwd=repo, check=True)

    attribute = subprocess.run(
        ["git", "check-attr", "filter", "--", "src/dp_scenarios/pgfixture/rows.csv"],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    )
    staged = subprocess.run(
        ["git", "show", ":src/dp_scenarios/pgfixture/.gitattributes"],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    )
    assert attribute.stdout.strip().endswith("filter: unset")
    assert "*.csv -filter -diff -merge text" in staged.stdout


@pytest.mark.integration
def test_live_rotation_observes_each_step_at_connection_level() -> None:
    fixture = PostgresFixture(29)
    try:
        with fixture:
            assert fixture.current_step == 0
            assert fixture.history[0]["observations"]["inventory_query_succeeds"] is True

            admin = fixture._admin
            role = fixture.credentials
            assert admin is not None
            assert admin.password != role.password

            for wrong_credentials in (
                replace(role, password=admin.password),
                replace(admin, password=role.password),
            ):
                with pytest.raises(psycopg.OperationalError):
                    fixture.connect(wrong_credentials)

            with fixture.connect() as connection:
                with connection.cursor() as cursor:
                    cursor.execute(
                        "SELECT nspname FROM pg_catalog.pg_namespace "
                        "WHERE nspname = 'lookup'"
                    )
                    assert cursor.fetchall() == [("lookup",)]

            step_one = fixture.advance_rotation()
            assert step_one.step == 1
            assert step_one["observations"] == {
                "fixture_step": 1,
                "connection_level_coverage": "executed",
                "login_succeeds": True,
                "inventory_query_succeeds": False,
                "inventory_query_failure": "insufficient_privilege",
                "lookup_catalog_visible": True,
                "lookup_information_schema_visible": False,
                "lookup_relations_catalog_visible": True,
                "lookup_query_denied": True,
            }

            with pytest.raises(Exception) as query_error:
                with fixture.connect() as connection:
                    with connection.cursor() as cursor:
                        cursor.execute("SELECT count(*) FROM inventory.line_items")
            assert getattr(query_error.value, "sqlstate", None) == "42501"

            old = fixture.credentials
            step_two = fixture.advance_rotation()
            assert step_two.step == 2
            old_login_succeeds = False
            try:
                with fixture.connect(old):
                    old_login_succeeds = True
            except psycopg.OperationalError:
                pass
            assert step_two["observations"]["old_credential_login_succeeds"] is old_login_succeeds
            assert step_two["observations"]["new_credential_login_succeeds"] is True
            assert step_two["observations"]["new_credential_lookup_catalog_visible"] is True
            assert step_two["observations"]["new_credential_lookup_information_schema_visible"] is False
            assert step_two["observations"]["new_credential_lookup_relations_catalog_visible"] is True
            assert step_two["observations"]["new_credential_lookup_query_denied"] is True
            assert old.password != fixture.credentials.password
            with fixture.connect() as connection:
                with connection.cursor() as cursor:
                    cursor.execute("SELECT count(*) FROM inventory.line_items")
                    assert cursor.fetchone()[0] > 0
            assert [record.step for record in fixture.history] == [0, 1, 2]
            evidence = fixture.oracle_records
    except FixtureUnavailable as error:
        skip_unavailable(error)
    assert [record["step"] for record in evidence] == [0, 1, 2]


@pytest.mark.integration
def test_live_rotation_rejects_reissued_old_credential() -> None:
    fixture = PostgresFixture(29)
    try:
        with fixture:
            fixture.advance_rotation()
            old_credentials = fixture.credentials
            fixture._new_password = lambda *, excluding=(): old_credentials.password  # type: ignore[method-assign]

            with pytest.raises(RotationError, match="old credential still authenticated"):
                fixture.advance_rotation()
    except FixtureUnavailable as error:
        skip_unavailable(error)

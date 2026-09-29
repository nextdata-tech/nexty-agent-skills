"""Deterministic and live connection-level checks for the rotation Postgres fixture."""

from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path
import secrets
import shutil
import subprocess

import psycopg
import pytest

from dp_scenarios.pgfixture import (
    ConnectionInfo,
    DATASET_GRAIN_TRAP,
    DATASET_INVENTORY_ROTATION,
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


B10_GOLD = Path(__file__).parents[1] / "scenarios/inventory-credential-rotation/gold"


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


# --------------------------------------------------------------------------
# B10 W2: inventory_rotation dataset support, probe table, pinned rotation
# password (deterministic; no container required)
# --------------------------------------------------------------------------


def test_seed_inventory_defaults_to_grain_trap_and_stays_byte_compatible(tmp_path: Path) -> None:
    default = seed_inventory(29, tmp_path / "default")
    explicit = seed_inventory(29, tmp_path / "explicit", dataset=DATASET_GRAIN_TRAP)

    assert default.dataset == DATASET_GRAIN_TRAP
    assert default.primary_table == "line_items"
    assert default.probe_table == "product_catalog"
    assert default.tables == explicit.tables
    assert default.gold_rows == explicit.gold_rows
    assert default.lookup_rows == explicit.lookup_rows
    assert set(default.table_ddl) == {"orders", "line_items"}


def test_seed_inventory_rejects_an_unsupported_dataset(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="unsupported pgfixture dataset"):
        seed_inventory(29, tmp_path, dataset="not-a-real-dataset")


def test_postgres_fixture_rejects_an_unsupported_dataset() -> None:
    with pytest.raises(ValueError, match="unsupported pgfixture dataset"):
        PostgresFixture(29, dataset="not-a-real-dataset")


def test_seed_inventory_rotation_matches_the_committed_b10_gold(tmp_path: Path) -> None:
    first = seed_inventory(29, tmp_path / "first", dataset=DATASET_INVENTORY_ROTATION)
    second = seed_inventory(29, tmp_path / "second", dataset=DATASET_INVENTORY_ROTATION)

    assert first.dataset == DATASET_INVENTORY_ROTATION
    assert first.primary_table == "inventory_positions"
    assert first.probe_table == "warehouse_directory"
    assert set(first.table_ddl) == {"warehouses", "inventory_positions"}
    assert first.tables == second.tables
    assert first.gold_rows == second.gold_rows
    assert first.orphan_count == 2
    assert first.negative_quantity_count == 1
    assert len(first.tables["warehouses"]) == 3
    assert len(first.tables["inventory_positions"]) == 8

    committed_answer = json.loads((B10_GOLD / "inventory_rotation_answer.json").read_text(encoding="utf-8"))
    committed_diagnostics = json.loads(
        (B10_GOLD / "inventory_rotation_diagnostics.json").read_text(encoding="utf-8")
    )
    assert list(first.gold_rows) == committed_answer
    assert committed_diagnostics["orphan_warehouse_count"] == first.orphan_count
    assert committed_diagnostics["negative_quantity_count"] == first.negative_quantity_count

    # The hidden probe table is unrelated business content, deterministic per
    # seed, and keyed off the (also deterministic) warehouse ids.
    assert {row["warehouse_id"] for row in first.lookup_rows} == {
        row["warehouse_id"] for row in first.tables["warehouses"]
    }


def test_advance_rotation_rejects_new_password_for_step_one() -> None:
    fixture = PostgresFixture(29)
    fixture._container_id = "container"
    fixture._admin = ConnectionInfo("127.0.0.1", 5432, "fixture", "postgres", "admin")
    fixture._credentials = ConnectionInfo("127.0.0.1", 5432, "fixture", "inventory_reader", "reader")
    fixture._history = [RotationRecord(0, "steady_state", (), {}, None)]
    fixture._live_step = 0

    with pytest.raises(RotationError, match="new_password is only accepted"):
        fixture.advance_rotation(1, new_password="whatever-secret")


# --------------------------------------------------------------------------
# B10 W2: container integration coverage for the inventory_rotation dataset
# --------------------------------------------------------------------------


@pytest.mark.integration
def test_live_inventory_rotation_dataset_seeds_and_probes_the_configured_table() -> None:
    fixture = PostgresFixture(29, dataset=DATASET_INVENTORY_ROTATION)
    try:
        with fixture:
            assert fixture.current_step == 0
            observations = fixture.history[0]["observations"]
            assert observations["inventory_query_succeeds"] is True
            assert observations["inventory_row_count"] == 8
            assert observations["lookup_query_denied"] is True
            assert observations["lookup_relations_catalog_visible"] is True

            with fixture.connect() as connection:
                with connection.cursor() as cursor:
                    cursor.execute(
                        "SELECT c.relname FROM pg_catalog.pg_class AS c "
                        "JOIN pg_catalog.pg_namespace AS n ON n.oid = c.relnamespace "
                        "WHERE n.nspname = 'lookup' AND c.relkind = 'r'"
                    )
                    assert cursor.fetchall() == [("warehouse_directory",)]
    except FixtureUnavailable as error:
        skip_unavailable(error)


@pytest.mark.integration
def test_live_inventory_rotation_dataset_completes_the_full_rotation_with_a_pinned_password() -> None:
    """Drive both rotation steps against the ``inventory_rotation`` dataset,
    checking the 42501 step-1 privilege failure and the step-2 old-credential
    failure, with the new password pinned by the caller instead of
    fixture-generated (the shape B10's E2 ``credential_fumble`` card needs).
    """

    fixture = PostgresFixture(29, dataset=DATASET_INVENTORY_ROTATION)
    try:
        with fixture:
            step_one = fixture.advance_rotation()
            assert step_one.step == 1
            assert step_one["observations"]["inventory_query_succeeds"] is False
            assert step_one["observations"]["inventory_query_failure"] == "insufficient_privilege"

            with pytest.raises(Exception) as query_error:
                with fixture.connect() as connection:
                    with connection.cursor() as cursor:
                        cursor.execute("SELECT count(*) FROM inventory.inventory_positions")
            assert getattr(query_error.value, "sqlstate", None) == "42501"

            old_credentials = fixture.credentials
            pinned_password = secrets.token_urlsafe(24)
            step_two = fixture.advance_rotation(new_password=pinned_password)
            assert step_two.step == 2
            assert fixture.credentials.password == pinned_password
            assert step_two["observations"]["new_credential_inventory_query_succeeds"] is True

            old_login_succeeds = False
            try:
                with fixture.connect(old_credentials):
                    old_login_succeeds = True
            except psycopg.OperationalError:
                pass
            assert old_login_succeeds is False
            assert step_two["observations"]["old_credential_login_succeeds"] is False

            with fixture.connect() as connection:
                with connection.cursor() as cursor:
                    cursor.execute("SELECT count(*) FROM inventory.inventory_positions")
                    assert cursor.fetchone()[0] == 8
    except FixtureUnavailable as error:
        skip_unavailable(error)


@pytest.mark.integration
def test_live_inventory_rotation_rejects_a_new_password_that_reuses_the_old_one() -> None:
    fixture = PostgresFixture(29, dataset=DATASET_INVENTORY_ROTATION)
    try:
        with fixture:
            fixture.advance_rotation()  # step 1
            reused_password = fixture.credentials.password
            with pytest.raises(ValueError, match="must differ from the admin and current role passwords"):
                fixture.advance_rotation(new_password=reused_password)
    except FixtureUnavailable as error:
        skip_unavailable(error)

"""Owned-container Postgres fixture with an explicit credential rotation."""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from dataclasses import dataclass, field
import secrets
import shutil
import subprocess
import tempfile
import time
from types import MappingProxyType
from typing import Any, NoReturn
from urllib.parse import quote

from .seed import SeededData, seed_inventory


SKIP_UNAVAILABLE_MARKER = "SKIP_FIXTURE_UNAVAILABLE"
FIXTURE_UNAVAILABLE_MARKER = SKIP_UNAVAILABLE_MARKER
_POSTGRES_IMAGE = "postgres:16-alpine"
_DATABASE = "fixture"
_ADMIN_ROLE = "postgres"
_EVALUATION_ROLE = "inventory_reader"
_INVENTORY_SCHEMA = "inventory"
_LOOKUP_SCHEMA = "lookup"
_CONTAINER_LABEL = "dp-scenarios.pgfixture.owner"
_LOOPBACK = "127.0.0.1"
_REDACTED = "[REDACTED]"


class FixtureUnavailable(RuntimeError):
    """The host cannot provide a dependency required by this fixture."""

    marker = SKIP_UNAVAILABLE_MARKER

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(f"{self.marker}: {reason}")


class FixtureSafetyError(RuntimeError):
    """The fixture cannot prove that a destructive operation is local/owned."""


class RotationError(RuntimeError):
    """A rotation step did not produce its declared connection-level result."""


@dataclass(frozen=True)
class ConnectionInfo:
    """Credentials handed to the scenario agent; the password is not repr-safe."""

    host: str
    port: int
    database: str
    user: str
    password: str = field(repr=False)

    def connect_kwargs(self) -> dict[str, Any]:
        return {
            "host": self.host,
            "port": self.port,
            "dbname": self.database,
            "user": self.user,
            "password": self.password,
        }

    def as_dict(self) -> dict[str, Any]:
        return {
            "host": self.host,
            "port": self.port,
            "database": self.database,
            "user": self.user,
            "password": self.password,
        }

    def redacted_dict(self) -> dict[str, Any]:
        """Return connection metadata without disclosing the password."""

        value = self.as_dict()
        value["password"] = _REDACTED
        return value

    @property
    def dsn(self) -> str:
        return (
            f"postgresql://{quote(self.user, safe='')}:{quote(self.password, safe='')}"
            f"@{self.host}:{self.port}/{quote(self.database, safe='')}"
        )


@dataclass(frozen=True)
class RotationRecord(Mapping[str, Any]):
    """Machine-readable oracle record for one explicit fixture state."""

    step: int
    state: str
    changed: tuple[str, ...]
    observations: Mapping[str, Any]
    credential: ConnectionInfo | None = field(default=None, repr=False)

    def to_dict(self) -> dict[str, Any]:
        return {
            "step": self.step,
            "state": self.state,
            "changed": list(self.changed),
            "observations": dict(self.observations),
            "credential": self.credential.redacted_dict() if self.credential is not None else None,
        }

    as_dict = to_dict

    def __getitem__(self, key: str) -> Any:
        return self.to_dict()[key]

    def __iter__(self) -> Iterator[str]:
        return iter(self.to_dict())

    def __len__(self) -> int:
        return len(self.to_dict())

    @property
    def changes(self) -> tuple[str, ...]:
        """Compatibility spelling for callers that call the field changes."""

        return self.changed


def skip_unavailable(error: FixtureUnavailable) -> NoReturn:
    """Turn a fixture-unavailable error into an explicit pytest skip."""

    if not isinstance(error, FixtureUnavailable):
        raise TypeError("skip_unavailable expects FixtureUnavailable")
    try:
        import pytest
    except ImportError as exc:  # pragma: no cover - only possible outside uv test env
        raise error from exc
    pytest.skip(
        f"{error}; connection-level integration coverage was not executed"
    )


def _identifier(value: str) -> str:
    """Quote an internal identifier; callers never pass SQL-derived input."""

    return '"' + value.replace('"', '""') + '"'


class PostgresFixture:
    """A disposable Postgres source owned by one fixture instance."""

    def __init__(
        self,
        seed: int,
        *,
        image: str = _POSTGRES_IMAGE,
        docker_binary: str = "docker",
        readiness_timeout: float = 30.0,
        initial_password: str | None = None,
    ) -> None:
        if isinstance(seed, bool) or not isinstance(seed, int) or seed < 0:
            raise ValueError("seed must be a non-negative integer")
        if not image.strip():
            raise ValueError("image must be non-empty")
        if readiness_timeout <= 0:
            raise ValueError("readiness_timeout must be positive")
        self.seed = seed
        self.image = image
        self.docker_binary = docker_binary
        self.readiness_timeout = readiness_timeout
        if initial_password is not None and (
            not isinstance(initial_password, str) or not initial_password
        ):
            raise ValueError("initial_password must be a non-empty string")
        self._admin_password = initial_password or secrets.token_urlsafe(24)
        self._role_password = self._new_password(excluding=(self._admin_password,))
        self._owner_token = secrets.token_hex(16)
        self._container_name = f"dp-pgfixture-{self._owner_token[:12]}"
        self._container_id: str | None = None
        self._host_port: int | None = None
        self._admin: ConnectionInfo | None = None
        self._credentials: ConnectionInfo | None = None
        self._seeded: SeededData | None = None
        self._history: list[RotationRecord] = []
        self._live_step = -1
        self._driver: Any = None
        self._temporary: Any = None

    def __enter__(self) -> "PostgresFixture":
        return self.start()

    def __exit__(self, exc_type: Any, exc_value: Any, traceback: Any) -> None:
        self.stop()

    @property
    def started(self) -> bool:
        return self._container_id is not None

    @property
    def current_step(self) -> int:
        return self._live_step if self.started else -1

    @property
    def state(self) -> str:
        return self._history[-1].state if self.started and self._history else "stopped"

    @property
    def history(self) -> tuple[RotationRecord, ...]:
        return tuple(self._history)

    rotation_history = history
    rotation_records = history

    @property
    def oracle_records(self) -> tuple[Mapping[str, Any], ...]:
        """Return immutable records suitable for a grading artifact."""

        return tuple(MappingProxyType(record.to_dict()) for record in self._history)

    @property
    def credentials(self) -> ConnectionInfo:
        if self._credentials is None:
            raise RuntimeError("Postgres fixture has not started")
        return self._credentials

    @property
    def connection_info(self) -> ConnectionInfo:
        return self.credentials

    @property
    def dsn(self) -> str:
        return self.credentials.dsn

    @property
    def gold_rows(self) -> tuple[Mapping[str, Any], ...]:
        if self._seeded is None:
            raise RuntimeError("Postgres fixture has not started")
        return self._seeded.gold_rows

    @property
    def seeded_data(self) -> SeededData:
        if self._seeded is None:
            raise RuntimeError("Postgres fixture has not started")
        return self._seeded

    @property
    def gold(self) -> tuple[Mapping[str, Any], ...]:
        return self.gold_rows

    def connect(self, credentials: ConnectionInfo | None = None) -> Any:
        """Open a fresh role connection; callers own and close the result."""

        if not self.started:
            raise RuntimeError("Postgres fixture has not started")
        return self._connect(credentials or self.credentials)

    def start(self) -> "PostgresFixture":
        """Create, initialize, and query-probe the owned container."""

        if self.started:
            return self
        self._history.clear()
        self._live_step = -1
        self._admin = None
        self._credentials = None
        self._seeded = None
        self._host_port = None
        self._ensure_runtime()
        try:
            self._temporary = tempfile.TemporaryDirectory(prefix="dp-pgfixture-")
            self._seeded = seed_inventory(self.seed, self._temporary.name)
            self._run_docker(
                [
                    "run",
                    "--detach",
                    "--rm",
                    "--name",
                    self._container_name,
                    "--label",
                    f"{_CONTAINER_LABEL}={self._owner_token}",
                    "--publish",
                    f"{_LOOPBACK}::5432",
                    "--env",
                    "POSTGRES_DB=" + _DATABASE,
                    "--env",
                    "POSTGRES_USER=" + _ADMIN_ROLE,
                    "--env",
                    "POSTGRES_PASSWORD=" + self._admin_password,
                    self.image,
                ]
            )
            self._container_id, actual_name = self._inspect_owned_container()
            if actual_name != self._container_name:
                raise FixtureSafetyError("created container name changed unexpectedly")
            self._host_port = self._published_port()
            self._admin = ConnectionInfo(
                _LOOPBACK, self._host_port, _DATABASE, _ADMIN_ROLE, self._admin_password
            )
            self._wait_until_ready()
            self._initialize_database()
            self._credentials = ConnectionInfo(
                _LOOPBACK, self._host_port, _DATABASE, _EVALUATION_ROLE, self._role_password
            )
            observations = self._probe_steady_state(self._credentials)
            self._history = [
                RotationRecord(
                    0,
                    "steady_state",
                    (
                        "container_created",
                        "inventory_seeded",
                        "lookup_schema_catalog_visible_but_select_denied",
                        "least_privilege_grants_applied",
                    ),
                    observations,
                    self._credentials,
                )
            ]
            self._live_step = 0
            return self
        except Exception:
            self.stop()
            raise

    def advance_rotation(self, step: int | None = None) -> RotationRecord:
        """Explicitly advance exactly one rotation step and return its oracle record."""

        if not self.started or self._admin is None or self._credentials is None:
            raise RuntimeError("Postgres fixture has not started")
        target = self._live_step + 1 if step is None else step
        if target != self._live_step + 1 or target not in {1, 2}:
            raise RotationError(f"rotation must advance one step from {self._live_step}")
        try:
            if target == 1:
                record = self._rotate_select_revoke()
            else:
                record = self._rotate_full_revoke()
            self._history.append(record)
            self._live_step = record.step
            return record
        except Exception:
            self.stop()
            raise

    advance = advance_rotation
    rotate = advance_rotation

    def stop(self) -> None:
        """Remove only this fixture's owned container; safe to call repeatedly."""

        container_id = self._container_id or self._find_owned_container_id()
        temporary = self._temporary
        try:
            if container_id is not None:
                try:
                    self._run_docker(["rm", "--force", container_id], check=False)
                except FixtureUnavailable:
                    # The daemon may disappear during teardown.  There is no
                    # safe non-Docker fallback, but local state must still clear
                    # and a second stop must remain harmless.
                    pass
        finally:
            self._container_id = None
            self._host_port = None
            self._admin = None
            self._credentials = None
            self._seeded = None
            self._live_step = -1
            self._temporary = None
            if temporary is not None:
                temporary.cleanup()

    close = stop

    def _load_driver(self) -> Any:
        if self._driver is not None:
            return self._driver
        try:
            import psycopg
        except ImportError as exc:  # pragma: no cover - dependency is declared in pyproject
            raise FixtureUnavailable("psycopg is not installed") from exc
        self._driver = psycopg
        return psycopg

    def _ensure_runtime(self) -> None:
        if shutil.which(self.docker_binary) is None:
            raise FixtureUnavailable(f"container runtime {self.docker_binary!r} is unavailable")
        self._load_driver()
        info = self._run_docker(["info"], check=False)
        if info.returncode != 0:
            detail = (info.stderr or info.stdout or "daemon did not answer").strip()
            raise FixtureUnavailable(f"Docker daemon is unavailable: {detail}")
        image = self._run_docker(["image", "inspect", self.image], check=False)
        if image.returncode != 0:
            raise FixtureUnavailable(f"Postgres image {self.image!r} is unavailable locally")

    def _run_docker(self, args: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
        try:
            result = subprocess.run(
                [self.docker_binary, *args],
                text=True,
                capture_output=True,
                check=check,
            )
        except OSError as exc:
            raise FixtureUnavailable(f"could not execute {self.docker_binary!r}: {exc}") from exc
        if check and result.returncode != 0:
            detail = (result.stderr or result.stdout or "docker command failed").strip()
            raise FixtureUnavailable(f"Docker command failed: {detail}")
        return result

    def _inspect_owned_container(self) -> tuple[str, str]:
        try:
            result = self._run_docker(
                [
                    "inspect",
                    "--format={{.Id}}\t{{index .Config.Labels \"dp-scenarios.pgfixture.owner\"}}\t{{.Name}}",
                    self._container_name,
                ]
            )
        except FixtureUnavailable as exc:
            raise FixtureSafetyError("could not verify the fixture container ownership") from exc
        parts = result.stdout.strip().split("\t")
        if len(parts) != 3:
            raise FixtureSafetyError("container inspection returned an invalid ownership record")
        container_id, owner, name = parts
        if owner != self._owner_token or name.lstrip("/") != self._container_name:
            raise FixtureSafetyError("container ownership label/name did not match")
        return container_id, name.lstrip("/")

    def _find_owned_container_id(self) -> str | None:
        if not self._container_name:
            return None
        try:
            result = self._run_docker(
                [
                    "ps",
                    "--all",
                    "--quiet",
                    "--filter",
                    f"name=^{self._container_name}$",
                    "--filter",
                    f"label={_CONTAINER_LABEL}={self._owner_token}",
                ],
                check=False,
            )
        except FixtureUnavailable:
            return None
        if result.returncode != 0:
            return None
        candidates = [line.strip() for line in result.stdout.splitlines() if line.strip()]
        return candidates[0] if len(candidates) == 1 else None

    def _assert_owned(self) -> None:
        if self._container_id is None or self._host_port is None:
            raise FixtureSafetyError("fixture has no owned running container")
        if self._admin is None or self._admin.host != _LOOPBACK:
            raise FixtureSafetyError("destructive operation is not loopback-scoped")
        actual_id, actual_name = self._inspect_owned_container()
        if actual_id != self._container_id or actual_name != self._container_name:
            raise FixtureSafetyError("destructive operation target is not the created container")

    def _published_port(self) -> int:
        result = self._run_docker(["port", self._container_name, "5432/tcp"])
        for line in result.stdout.splitlines():
            value = line.strip()
            if value.startswith(_LOOPBACK + ":"):
                try:
                    port = int(value.rsplit(":", 1)[1])
                except ValueError:
                    continue
                if 1 <= port <= 65535:
                    return port
        raise FixtureSafetyError("container port was not published on loopback")

    def _connect(self, credentials: ConnectionInfo) -> Any:
        if credentials.host != _LOOPBACK:
            raise FixtureSafetyError("fixture connections must use loopback")
        return self._load_driver().connect(**credentials.connect_kwargs(), connect_timeout=3)

    def _wait_until_ready(self) -> None:
        assert self._admin is not None
        deadline = time.monotonic() + self.readiness_timeout
        last_error: Exception | None = None
        while time.monotonic() < deadline:
            connection = None
            try:
                connection = self._connect(self._admin)
                with connection.cursor() as cursor:
                    cursor.execute("SELECT 1")
                    if cursor.fetchone() != (1,):
                        raise RuntimeError("Postgres readiness query returned an unexpected row")
                connection.close()
                return
            except Exception as exc:
                last_error = exc
                if connection is not None:
                    connection.close()
                time.sleep(0.05)
        raise FixtureUnavailable(f"Postgres did not accept SELECT 1 before readiness deadline: {last_error}")

    def _initialize_database(self) -> None:
        assert self._admin is not None and self._seeded is not None
        # This assertion deliberately precedes the first REVOKE below.  The
        # database is disposable, but destructive SQL still requires proof of
        # the exact container and loopback target.
        self._assert_owned()
        connection = self._connect(self._admin)
        try:
            connection.autocommit = True
            with connection.cursor() as cursor:
                cursor.execute("CREATE SCHEMA " + _identifier(_INVENTORY_SCHEMA))
                cursor.execute("CREATE SCHEMA " + _identifier(_LOOKUP_SCHEMA))
                cursor.execute(
                    self._role_password_sql(
                        "CREATE ROLE {} LOGIN PASSWORD {} NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT",
                        _EVALUATION_ROLE,
                        self._role_password,
                    )
                )
                cursor.execute(
                    "CREATE TABLE inventory.orders ("
                    "order_id text NOT NULL, region text NOT NULL, "
                    "order_timestamp timestamptz NOT NULL, order_amount numeric(18,2) NOT NULL, "
                    "status text NOT NULL)"
                )
                cursor.execute(
                    "CREATE TABLE inventory.line_items ("
                    "line_item_id text NOT NULL, order_id text NOT NULL, product text NOT NULL, "
                    "quantity integer NOT NULL, unit_price numeric(18,2) NOT NULL)"
                )
                cursor.execute(
                    "CREATE TABLE lookup.product_catalog ("
                    "product text PRIMARY KEY, category text NOT NULL, "
                    "reference_price numeric(18,2) NOT NULL)"
                )
                cursor.executemany(
                    "INSERT INTO inventory.orders VALUES (%s, %s, %s, %s, %s)",
                    [
                        (
                            row["order_id"],
                            row["region"],
                            row["order_timestamp"],
                            row["order_amount"],
                            row["status"],
                        )
                        for row in self._seeded.tables["orders"]
                    ],
                )
                cursor.executemany(
                    "INSERT INTO inventory.line_items VALUES (%s, %s, %s, %s, %s)",
                    [
                        (
                            row["line_item_id"],
                            row["order_id"],
                            row["product"],
                            row["quantity"],
                            row["unit_price"],
                        )
                        for row in self._seeded.tables["line_items"]
                    ],
                )
                cursor.executemany(
                    "INSERT INTO lookup.product_catalog VALUES (%s, %s, %s)",
                    [
                        (row["product"], row["category"], row["reference_price"])
                        for row in self._seeded.lookup_rows
                    ],
                )
                cursor.execute("REVOKE ALL PRIVILEGES ON DATABASE " + _identifier(_DATABASE) + " FROM PUBLIC")
                cursor.execute(
                    "REVOKE ALL PRIVILEGES ON SCHEMA "
                    + _identifier(_INVENTORY_SCHEMA)
                    + ", "
                    + _identifier(_LOOKUP_SCHEMA)
                    + " FROM PUBLIC"
                )
                cursor.execute(
                    "REVOKE ALL PRIVILEGES ON ALL TABLES IN SCHEMA "
                    + _identifier(_INVENTORY_SCHEMA)
                    + ", "
                    + _identifier(_LOOKUP_SCHEMA)
                    + " FROM PUBLIC"
                )
                cursor.execute(
                    "GRANT CONNECT ON DATABASE "
                    + _identifier(_DATABASE)
                    + " TO "
                    + _identifier(_EVALUATION_ROLE)
                )
                cursor.execute(
                    "GRANT USAGE ON SCHEMA "
                    + _identifier(_INVENTORY_SCHEMA)
                    + " TO "
                    + _identifier(_EVALUATION_ROLE)
                )
                cursor.execute(
                    "GRANT SELECT ON ALL TABLES IN SCHEMA "
                    + _identifier(_INVENTORY_SCHEMA)
                    + " TO "
                    + _identifier(_EVALUATION_ROLE)
                )
                cursor.execute(
                    "REVOKE ALL PRIVILEGES ON SCHEMA "
                    + _identifier(_LOOKUP_SCHEMA)
                    + " FROM "
                    + _identifier(_EVALUATION_ROLE)
                )
                cursor.execute(
                    "REVOKE ALL PRIVILEGES ON ALL TABLES IN SCHEMA "
                    + _identifier(_LOOKUP_SCHEMA)
                    + " FROM "
                    + _identifier(_EVALUATION_ROLE)
                )
        finally:
            connection.close()

    def _probe_steady_state(self, credentials: ConnectionInfo) -> Mapping[str, Any]:
        lookup = self._probe_lookup_visibility(credentials)
        connection = self._connect(credentials)
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT count(*) FROM inventory.line_items")
                row_count = cursor.fetchone()[0]
        finally:
            connection.close()
        if not isinstance(row_count, int) or row_count <= 0:
            raise RotationError("step 0 inventory query returned no seeded rows")
        if not lookup["query_denied"]:
            raise RotationError("step 0 lookup query was unexpectedly allowed")
        if not lookup["relations_catalog_visible"]:
            raise RotationError("step 0 lookup table was not present in the catalog")
        return {
            "fixture_step": 0,
            "connection_level_coverage": "executed",
            "login_succeeds": True,
            "inventory_query_succeeds": True,
            "inventory_row_count": row_count,
            "lookup_catalog_visible": lookup["catalog_visible"],
            "lookup_information_schema_visible": lookup["information_schema_visible"],
            "lookup_relations_catalog_visible": lookup["relations_catalog_visible"],
            "lookup_query_denied": True,
        }

    def _probe_lookup_visibility(self, credentials: ConnectionInfo) -> Mapping[str, bool]:
        """Report actual catalog visibility and table denial in a fresh session.

        ``information_schema`` hides the schema from this role, but PostgreSQL's
        ``pg_namespace`` and ``pg_class`` catalogs are readable by PUBLIC.  The
        latter is the visibility an agent using ``\\dn``/catalog SQL observes.
        """

        connection = self._connect(credentials)
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT nspname FROM pg_catalog.pg_namespace "
                    "WHERE nspname = 'lookup'"
                )
                catalog_visible = cursor.fetchone() is not None
                cursor.execute(
                    "SELECT schema_name FROM information_schema.schemata "
                    "WHERE schema_name = 'lookup'"
                )
                information_schema_visible = cursor.fetchone() is not None
                cursor.execute(
                    "SELECT c.relname FROM pg_catalog.pg_class AS c "
                    "JOIN pg_catalog.pg_namespace AS n ON n.oid = c.relnamespace "
                    "WHERE n.nspname = 'lookup' AND c.relname = 'product_catalog'"
                )
                relations_catalog_visible = cursor.fetchone() is not None
                query_denied = self._lookup_query_denied(cursor)
        finally:
            connection.close()
        return {
            "catalog_visible": catalog_visible,
            "information_schema_visible": information_schema_visible,
            "relations_catalog_visible": relations_catalog_visible,
            "query_denied": query_denied,
        }

    @staticmethod
    def _lookup_query_denied(cursor: Any) -> bool:
        try:
            cursor.execute("SELECT count(*) FROM lookup.product_catalog")
        except Exception as exc:
            return getattr(exc, "sqlstate", None) == "42501"
        return False

    @staticmethod
    def _new_password(*, excluding: tuple[str, ...] = ()) -> str:
        excluded = set(excluding)
        password = secrets.token_urlsafe(24)
        while password in excluded:
            password = secrets.token_urlsafe(24)
        return password

    def _role_password_sql(self, template: str, role: str, password: str) -> Any:
        """Compose password-bearing role DDL without interpolating raw secrets."""

        sql = self._load_driver().sql
        return sql.SQL(template).format(sql.Identifier(role), sql.Literal(password))

    def _rotate_select_revoke(self) -> RotationRecord:
        assert self._admin is not None and self._credentials is not None
        self._assert_owned()
        connection = self._connect(self._admin)
        try:
            connection.autocommit = True
            with connection.cursor() as cursor:
                cursor.execute(
                    "REVOKE SELECT ON ALL TABLES IN SCHEMA "
                    + _identifier(_INVENTORY_SCHEMA)
                    + " FROM "
                    + _identifier(_EVALUATION_ROLE)
                )
        finally:
            connection.close()

        lookup = self._probe_lookup_visibility(self._credentials)
        fresh = None
        login_succeeds = False
        query_failed_with_permission = False
        try:
            fresh = self._connect(self._credentials)
            login_succeeds = True
            try:
                with fresh.cursor() as cursor:
                    cursor.execute("SELECT count(*) FROM inventory.line_items")
            except Exception as exc:
                sqlstate = getattr(exc, "sqlstate", None)
                if sqlstate != "42501":
                    raise RotationError(
                        f"step 1 query failed for an unexpected reason: {sqlstate or exc}"
                    ) from exc
                query_failed_with_permission = True
            else:
                query_failed_with_permission = False
        finally:
            if fresh is not None:
                fresh.close()
        if not login_succeeds or not query_failed_with_permission:
            raise RotationError("step 1 did not retain login while revoking SELECT")
        if not lookup["query_denied"] or not lookup["relations_catalog_visible"]:
            raise RotationError("step 1 lookup catalog/query result changed unexpectedly")
        return RotationRecord(
            1,
            "select_revoked_login_retained",
            ("select_revoked_on_inventory",),
            {
                "fixture_step": 1,
                "connection_level_coverage": "executed",
                "login_succeeds": login_succeeds,
                "inventory_query_succeeds": False,
                "inventory_query_failure": "insufficient_privilege",
                "lookup_catalog_visible": lookup["catalog_visible"],
                "lookup_information_schema_visible": lookup["information_schema_visible"],
                "lookup_relations_catalog_visible": lookup["relations_catalog_visible"],
                "lookup_query_denied": lookup["query_denied"],
            },
            self._credentials,
        )

    def _rotate_full_revoke(self) -> RotationRecord:
        assert self._admin is not None and self._credentials is not None
        self._assert_owned()
        old_credentials = self._credentials
        new_password = self._new_password(
            excluding=(self._admin_password, old_credentials.password)
        )
        connection = self._connect(self._admin)
        try:
            connection.autocommit = False
            with connection.cursor() as cursor:
                cursor.execute(
                    "REVOKE ALL PRIVILEGES ON DATABASE "
                    + _identifier(_DATABASE)
                    + " FROM "
                    + _identifier(_EVALUATION_ROLE)
                )
                cursor.execute(
                    "REVOKE ALL PRIVILEGES ON SCHEMA "
                    + _identifier(_INVENTORY_SCHEMA)
                    + ", "
                    + _identifier(_LOOKUP_SCHEMA)
                    + " FROM "
                    + _identifier(_EVALUATION_ROLE)
                )
                cursor.execute(
                    "REVOKE ALL PRIVILEGES ON ALL TABLES IN SCHEMA "
                    + _identifier(_INVENTORY_SCHEMA)
                    + ", "
                    + _identifier(_LOOKUP_SCHEMA)
                    + " FROM "
                    + _identifier(_EVALUATION_ROLE)
                )
                cursor.execute(
                    "ALTER ROLE " + _identifier(_EVALUATION_ROLE) + " NOLOGIN PASSWORD NULL"
                )
                cursor.execute(
                    self._role_password_sql(
                        "ALTER ROLE {} LOGIN PASSWORD {}",
                        _EVALUATION_ROLE,
                        new_password,
                    )
                )
                cursor.execute(
                    "GRANT CONNECT ON DATABASE "
                    + _identifier(_DATABASE)
                    + " TO "
                    + _identifier(_EVALUATION_ROLE)
                )
                cursor.execute(
                    "GRANT USAGE ON SCHEMA "
                    + _identifier(_INVENTORY_SCHEMA)
                    + " TO "
                    + _identifier(_EVALUATION_ROLE)
                )
                cursor.execute(
                    "GRANT SELECT ON ALL TABLES IN SCHEMA "
                    + _identifier(_INVENTORY_SCHEMA)
                    + " TO "
                    + _identifier(_EVALUATION_ROLE)
                )
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

        new_credentials = ConnectionInfo(
            old_credentials.host,
            old_credentials.port,
            old_credentials.database,
            old_credentials.user,
            new_password,
        )
        old_login_succeeds = False
        old_connection = None
        try:
            old_connection = self._connect(old_credentials)
            old_login_succeeds = True
        except Exception:
            old_login_succeeds = False
        finally:
            if old_connection is not None:
                old_connection.close()
        if old_login_succeeds:
            raise RotationError("step 2 old credential still authenticated")

        fresh = self._connect(new_credentials)
        try:
            with fresh.cursor() as cursor:
                cursor.execute("SELECT count(*) FROM inventory.line_items")
                row_count = cursor.fetchone()[0]
        finally:
            fresh.close()
        if not isinstance(row_count, int) or row_count <= 0:
            raise RotationError("step 2 new credential could not read inventory")
        lookup = self._probe_lookup_visibility(new_credentials)
        if not lookup["query_denied"] or not lookup["relations_catalog_visible"]:
            raise RotationError("step 2 lookup catalog/query result changed unexpectedly")
        self._credentials = new_credentials
        return RotationRecord(
            2,
            "full_revoke_new_credential_issued",
            (
                "all_old_role_privileges_revoked",
                "old_login_disabled_and_password_invalidated",
                "new_password_issued",
                "least_privilege_inventory_access_reissued",
            ),
            {
                "fixture_step": 2,
                "connection_level_coverage": "executed",
                "old_credential_login_succeeds": old_login_succeeds,
                "new_credential_login_succeeds": True,
                "new_credential_inventory_query_succeeds": True,
                "new_credential_lookup_catalog_visible": lookup["catalog_visible"],
                "new_credential_lookup_information_schema_visible": lookup[
                    "information_schema_visible"
                ],
                "new_credential_lookup_relations_catalog_visible": lookup[
                    "relations_catalog_visible"
                ],
                "new_credential_lookup_query_denied": lookup["query_denied"],
            },
            new_credentials,
        )


PgFixture = PostgresFixture


__all__ = [
    "ConnectionInfo",
    "FIXTURE_UNAVAILABLE_MARKER",
    "FixtureSafetyError",
    "FixtureUnavailable",
    "PgFixture",
    "PostgresFixture",
    "RotationError",
    "RotationRecord",
    "SKIP_UNAVAILABLE_MARKER",
    "skip_unavailable",
]

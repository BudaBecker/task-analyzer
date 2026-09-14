"""Composition and startup verification for the Task Analyzer server.

Covers PCE-34, PCE-35, PCE-44 through PCE-47 (REQ-003, REQ-010,
REQ-027, REQ-028).

Composition is explicit and injectable: :func:`create_app` receives the
settings and the clock it runs with, so a test composes the real
application against its own disposable database and its own instant.
:func:`application_factory` is the runtime entry point named by the
service unit. It takes no arguments, reads the approved environment,
installs structured logging and then calls :func:`create_app`.

Neither factory initializes, migrates or creates a database. Startup
opens the configured database in existing-file mode and verifies that it
is the schema this server speaks, that the approved durability policy
took effect, and that the product configuration can be read. An absent
or incompatible database therefore stops the server visibly instead of
being silently created or quietly served against. A database that was
initialized but not yet configured is not incompatible: it starts, and
its configuration routes are what fix the product zone.
"""

from __future__ import annotations

import logging
import platform
import sqlite3
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from importlib import metadata

from fastapi import FastAPI

from task_analyzer_server import api, storage
from task_analyzer_server.clock import Clock, SystemClock
from task_analyzer_server.logging_config import configure_logging
from task_analyzer_server.settings import ServerSettings

SUPPORTED_SCHEMA_VERSION = 1
READ_SCHEMA_VERSION = (
    "SELECT version FROM schema_version WHERE schema_version_id = 1"
)

STARTUP_EVENT = "server_startup"
TIME_DATA_PACKAGE = "tzdata"
SYSTEM_TIME_DATA = "system"

_logger = logging.getLogger(__name__)


class StartupVerificationError(RuntimeError):
    """Raised when the configured database cannot serve this server.

    The message names the database path and what was wrong with it, so
    an operator sees which file to correct instead of a generic startup
    failure.
    """


def create_app(settings: ServerSettings, clock: Clock) -> FastAPI:
    """Compose the application from its settings and its clock.

    Args:
        settings: Validated runtime configuration of this process.
        clock: The server's source of the current instant.

    Returns:
        The composed application. Its database is verified when the
        application starts, not while it is being composed.
    """

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        """Verify the configured database before serving anything.

        Args:
            application: The application starting up.

        Yields:
            ``None``, once the database has been verified.
        """
        verify_database(settings)
        _logger.info(_startup_event())
        yield

    app = FastAPI(lifespan=lifespan)
    app.state.settings = settings
    app.state.clock = clock
    api.install_error_handlers(app)
    app.include_router(api.router)
    return app


def application_factory() -> FastAPI:
    """Build the application the way the service unit runs it.

    This is the zero-argument entry point behind
    ``task_analyzer_server.app:application_factory --factory``. It reads
    the approved environment, installs structured logging and composes
    the application. It creates no database.

    Returns:
        The composed application.

    Raises:
        SettingsError: If a required environment value is missing or any
            supplied value is invalid.
    """
    settings = ServerSettings.from_environment()
    configure_logging(settings.log_level)
    return create_app(settings, SystemClock())


def verify_database(settings: ServerSettings) -> None:
    """Confirm the configured database can serve this server.

    Opening the connection is itself part of the verification: it
    refuses to create a missing file and it confirms that every approved
    durability pragma took effect.

    Args:
        settings: Validated runtime configuration naming the database.

    Raises:
        StartupVerificationError: If the database is absent, unreadable,
            or not the schema version this server speaks.
        DurabilityPolicyError: If the connection does not report the
            approved durability policy.
    """
    try:
        with storage.open_connection(
            settings.database_path, settings.db_busy_timeout_ms
        ) as connection:
            _confirm_schema_version(connection, settings)
            storage.read_product_time_zone(connection)
    except sqlite3.Error as failure:
        raise StartupVerificationError(
            f"The database {settings.database_path} could not be opened"
            f" and read: {failure}. The server never creates, migrates"
            " or recreates a database, so initialize it explicitly"
            " before starting the service."
        ) from failure


def _confirm_schema_version(
    connection: sqlite3.Connection, settings: ServerSettings
) -> None:
    """Confirm the database speaks the schema this server speaks.

    Args:
        connection: The open connection to the configured database.
        settings: Validated runtime configuration naming the database.

    Raises:
        StartupVerificationError: If no version row exists or it names
            another version.
        sqlite3.Error: If the version cannot be read at all, which the
            caller reports as an unusable database.
    """
    row = connection.execute(READ_SCHEMA_VERSION).fetchone()
    version = None if row is None else int(row[0])
    if version != SUPPORTED_SCHEMA_VERSION:
        raise StartupVerificationError(
            f"The database {settings.database_path} reports schema"
            f" version {version!r} instead of the supported"
            f" {SUPPORTED_SCHEMA_VERSION}. The server never migrates a"
            " database, so it refuses to serve this one."
        )


def _startup_event() -> str:
    """Name the startup event and the versions it ran with.

    The approved log schema carries a fixed set of fields and none of
    them holds a version, so the versions belong to the event name. The
    name keeps a stable prefix, which is what an operator matches on.

    Returns:
        The startup event text.
    """
    return (
        f"{STARTUP_EVENT} runtime={platform.python_version()}"
        f" time_data={_time_data_version()}"
    )


def _time_data_version() -> str:
    """Name the IANA time-zone data this process resolves zones with.

    Returns:
        The installed ``tzdata`` version, or ``system`` when zones come
        from the host's own time-zone database.
    """
    try:
        return metadata.version(TIME_DATA_PACKAGE)
    except metadata.PackageNotFoundError:
        return SYSTEM_TIME_DATA

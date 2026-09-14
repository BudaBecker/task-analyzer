"""Composition and startup verification for the Task Analyzer server.

Covers PCE-34, PCE-35, PCE-44 through PCE-47 (REQ-003, REQ-010, REQ-027,
REQ-028).
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
    """Raised when the configured database cannot serve this server."""


def create_app(settings: ServerSettings, clock: Clock) -> FastAPI:
    """Compose the application from its settings and its clock."""

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        """Verify the configured database before serving anything."""
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
    """Build the application the way the service unit runs it."""
    settings = ServerSettings.from_environment()
    configure_logging(settings.log_level)
    return create_app(settings, SystemClock())


def verify_database(settings: ServerSettings) -> None:
    """Confirm the configured database can serve this server."""
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
    """Confirm the database speaks the schema this server speaks."""
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
    """Name the startup event and the versions it ran with."""
    return (
        f"{STARTUP_EVENT} runtime={platform.python_version()}"
        f" time_data={_time_data_version()}"
    )


def _time_data_version() -> str:
    """Name the IANA time-zone data this process resolves zones with."""
    try:
        return metadata.version(TIME_DATA_PACKAGE)
    except metadata.PackageNotFoundError:
        return SYSTEM_TIME_DATA

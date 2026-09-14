"""Explicit initialization of the Task Analyzer server database.

Covers PCE-34, PCE-35 and PCE-45 (REQ-003, REQ-010, REQ-028).

This module is the only entry point that creates a database. The
application never calls it: startup opens an existing database and fails
visibly when that database is absent or incompatible, so a running
server can neither initialize, migrate, nor recreate one. Running this
initializer against a real database is a separately authorized operator
step.

The packaged DDL is located through ``importlib.resources`` and applied
with standard ``sqlite3``. Nothing here depends on operational storage
helpers or on a source checkout being present.
"""

from __future__ import annotations

import sqlite3
from contextlib import closing
from importlib import resources
from pathlib import Path

PACKAGE_NAME = "task_analyzer_server"
INITIAL_SCHEMA_RESOURCE = "schema/001_initial.sql"


class DatabaseAlreadyExistsError(RuntimeError):
    """Raised when something already exists at the target path.

    The message names the path so an operator sees which file blocked
    initialization.
    """


def initialize_database(path: Path) -> None:
    """Create a new database from the packaged initial schema.

    The schema and its version row are installed inside one transaction.
    A failure removes the partially created file, so the outcome is
    either a complete database or none at all and a corrected attempt is
    not blocked by leftovers.

    Args:
        path: Location of the database file to create. Nothing may exist
            there yet.

    Raises:
        DatabaseAlreadyExistsError: If anything already exists at the
            path. An existing database is never recreated, migrated, or
            overwritten.
        sqlite3.Error: If the database cannot be created at that path.
    """
    if path.exists():
        raise DatabaseAlreadyExistsError(
            f"{path} already exists; initialization never recreates,"
            " migrates, or overwrites an existing database."
        )
    script = read_initial_schema()
    try:
        with closing(
            sqlite3.connect(path, isolation_level=None)
        ) as connection:
            connection.executescript(f"BEGIN IMMEDIATE;\n{script}\nCOMMIT;")
    except sqlite3.Error:
        path.unlink(missing_ok=True)
        raise


def read_initial_schema() -> str:
    """Read the packaged initial DDL.

    The resource is located through ``importlib.resources``, so the
    result does not depend on the current directory.

    Returns:
        The text of the initial schema script.
    """
    package_files = resources.files(PACKAGE_NAME)
    resource = package_files.joinpath(INITIAL_SCHEMA_RESOURCE)
    return resource.read_text(encoding="utf-8")

"""Explicit initialization of the Task Analyzer server database.

Covers PCE-34, PCE-35 and PCE-45 (REQ-003, REQ-010, REQ-028).
"""

from __future__ import annotations

import sqlite3
from contextlib import closing
from importlib import resources
from pathlib import Path

PACKAGE_NAME = "task_analyzer_server"
INITIAL_SCHEMA_RESOURCE = "schema/001_initial.sql"


class DatabaseAlreadyExistsError(RuntimeError):
    """Raised when something already exists at the target path."""


def initialize_database(path: Path) -> None:
    """Create a new database from the packaged initial schema."""
    script = read_initial_schema()
    try:
        # Only the exclusive creator owns failure cleanup for this path.
        with path.open("xb"):
            pass
    except FileExistsError:
        raise DatabaseAlreadyExistsError(
            f"{path} already exists; initialization never recreates,"
            " migrates, or overwrites an existing database."
        ) from None
    try:
        with closing(
            sqlite3.connect(path, isolation_level=None)
        ) as connection:
            connection.executescript(f"BEGIN IMMEDIATE;\n{script}\nCOMMIT;")
    except sqlite3.Error:
        path.unlink(missing_ok=True)
        raise


def read_initial_schema() -> str:
    """Read the packaged initial DDL."""
    package_files = resources.files(PACKAGE_NAME)
    resource = package_files.joinpath(INITIAL_SCHEMA_RESOURCE)
    return resource.read_text(encoding="utf-8")

"""Integration tests for product configuration storage.

Covers PCE-29, PCE-35; REQ-028.

Every test opens a newly allocated temporary database file created by
the explicit initializer. No test reads
``TASK_ANALYZER_DATABASE_PATH`` or touches any configured runtime
database.
"""

import sqlite3
from pathlib import Path

import pytest

from task_analyzer_server import schema, storage

BUSY_TIMEOUT_MS = 5000

PRODUCT_ZONE = "America/Sao_Paulo"
ANOTHER_ZONE = "Europe/Lisbon"
INJECTING_ZONE = "'); DROP TABLE tasks; --"

COUNT_CONFIGURATION = "SELECT COUNT(*) FROM product_configuration"
COUNT_TASK_TABLE = (
    "SELECT COUNT(*) FROM sqlite_master"
    " WHERE type = 'table' AND name = 'tasks'"
)


@pytest.fixture
def database_path(tmp_path: Path) -> Path:
    """Create a disposable initialized database file.

    Args:
        tmp_path: pytest-allocated temporary directory.

    Returns:
        Absolute path of the newly created database file.
    """
    path = tmp_path / "disposable.sqlite3"
    schema.initialize_database(path)
    return path


def set_zone(path: Path, zone_key: str) -> storage.ConfiguredZone:
    """Run one committed compare-and-set through its own connection.

    Args:
        path: Database file to write.
        zone_key: The IANA key to attempt.

    Returns:
        The outcome of the attempt.
    """
    with storage.open_connection(path, BUSY_TIMEOUT_MS) as connection:
        with storage.write_transaction(connection):
            return storage.store_product_time_zone(connection, zone_key)


def read_zone(path: Path) -> str | None:
    """Read the retained zone through a separate new connection.

    Args:
        path: Database file to read.

    Returns:
        The retained IANA key, or ``None`` when the singleton is unset.
    """
    with storage.open_connection(path, BUSY_TIMEOUT_MS) as connection:
        return storage.read_product_time_zone(connection)


def count(path: Path, statement: str) -> int:
    """Run one counting statement through a separate new connection.

    Args:
        path: Database file to read.
        statement: The counting statement to run.

    Returns:
        The counted number of rows.
    """
    with storage.open_connection(path, BUSY_TIMEOUT_MS) as connection:
        return int(connection.execute(statement).fetchone()[0])


def test_an_unconfigured_database_reports_no_zone(
    database_path: Path,
) -> None:
    """An unset singleton reports absence instead of a zone."""
    assert read_zone(database_path) is None


def test_the_first_setup_stores_the_requested_zone(
    database_path: Path,
) -> None:
    """The first attempt on an unset singleton stores its key."""
    stored = set_zone(database_path, PRODUCT_ZONE)

    assert stored == storage.ConfiguredZone(
        storage.ZoneOutcome.STORED, PRODUCT_ZONE
    )


def test_a_committed_zone_is_readable_by_a_new_connection(
    database_path: Path,
) -> None:
    """The stored zone survives the connection that wrote it."""
    set_zone(database_path, PRODUCT_ZONE)

    assert read_zone(database_path) == PRODUCT_ZONE


def test_repeating_the_same_key_reports_it_as_already_set(
    database_path: Path,
) -> None:
    """A repeated identical key is distinguished from a first setup."""
    set_zone(database_path, PRODUCT_ZONE)

    repeated = set_zone(database_path, PRODUCT_ZONE)

    assert repeated == storage.ConfiguredZone(
        storage.ZoneOutcome.ALREADY_SET, PRODUCT_ZONE
    )


def test_repeating_the_same_key_stores_no_second_row(
    database_path: Path,
) -> None:
    """The singleton stays a single row across repeated setups."""
    set_zone(database_path, PRODUCT_ZONE)
    set_zone(database_path, PRODUCT_ZONE)

    assert count(database_path, COUNT_CONFIGURATION) == 1


def test_a_different_key_is_reported_as_conflicting(
    database_path: Path,
) -> None:
    """A different key is distinguished and returns the retained zone."""
    set_zone(database_path, PRODUCT_ZONE)

    refused = set_zone(database_path, ANOTHER_ZONE)

    assert refused == storage.ConfiguredZone(
        storage.ZoneOutcome.CONFLICTING, PRODUCT_ZONE
    )


def test_a_different_key_never_replaces_the_retained_zone(
    database_path: Path,
) -> None:
    """The retained zone is unchanged after a different key arrives."""
    set_zone(database_path, PRODUCT_ZONE)

    set_zone(database_path, ANOTHER_ZONE)

    assert read_zone(database_path) == PRODUCT_ZONE
    assert count(database_path, COUNT_CONFIGURATION) == 1


def test_an_uncommitted_setup_retains_nothing(
    database_path: Path,
) -> None:
    """A setup whose transaction fails leaves the singleton unset."""
    with storage.open_connection(database_path, BUSY_TIMEOUT_MS) as connection:
        with pytest.raises(RuntimeError, match="injected"):
            with storage.write_transaction(connection):
                storage.store_product_time_zone(connection, PRODUCT_ZONE)
                raise RuntimeError("injected storage failure")

    assert read_zone(database_path) is None


def test_a_zone_key_is_bound_rather_than_concatenated(
    database_path: Path,
) -> None:
    """Statement text never carries the key, so no key can be SQL."""
    stored = set_zone(database_path, INJECTING_ZONE)

    assert stored.product_time_zone == INJECTING_ZONE
    assert read_zone(database_path) == INJECTING_ZONE
    assert count(database_path, COUNT_TASK_TABLE) == 1


def test_a_second_row_is_refused_by_the_singleton_key(
    database_path: Path,
) -> None:
    """The primary key backs the compare-and-set against stray writes."""
    set_zone(database_path, PRODUCT_ZONE)

    with storage.open_connection(database_path, BUSY_TIMEOUT_MS) as connection:
        with pytest.raises(sqlite3.IntegrityError):
            with storage.write_transaction(connection):
                connection.execute(
                    storage.INSERT_PRODUCT_TIME_ZONE, (ANOTHER_ZONE,)
                )

    assert read_zone(database_path) == PRODUCT_ZONE

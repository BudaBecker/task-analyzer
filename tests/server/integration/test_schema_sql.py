"""Integration tests for the versioned initial database schema.

Covers PCE-19, PCE-20, PCE-24, PCE-25, PCE-29; REQ-028, REQ-029, REQ-031.
"""

import sqlite3
from collections.abc import Iterator
from importlib import resources
from pathlib import Path

import pytest

INSERT_TASK = """
INSERT INTO tasks (
    task_id, title, title_key, observations, deadline_date,
    status, created_at_us, latest_completed_at_us, is_deleted
) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
"""

CREATED_AT_US = 1_757_721_600_000_000


def read_initial_schema() -> str:
    package_files = resources.files("task_analyzer_server")
    resource = package_files.joinpath("schema/001_initial.sql")
    return resource.read_text(encoding="utf-8")


@pytest.fixture
def database(tmp_path: Path) -> Iterator[sqlite3.Connection]:
    path = tmp_path / "disposable.sqlite3"
    connection = sqlite3.connect(path, isolation_level=None)
    connection.executescript(
        f"BEGIN IMMEDIATE;\n{read_initial_schema()}\nCOMMIT;"
    )
    try:
        yield connection
    finally:
        connection.close()


def insert_task(
    connection: sqlite3.Connection,
    task_id: str,
    title_key: str,
    *,
    title: str = "Pay the electricity bill",
    observations: str | None = None,
    deadline_date: str | None = None,
    status: str = "pending",
    latest_completed_at_us: int | None = None,
    is_deleted: int = 0,
) -> None:
    connection.execute(
        INSERT_TASK,
        (
            task_id,
            title,
            title_key,
            observations,
            deadline_date,
            status,
            CREATED_AT_US,
            latest_completed_at_us,
            is_deleted,
        ),
    )


def column_shape(
    connection: sqlite3.Connection, table: str
) -> list[tuple[str, str, int, int]]:
    rows = connection.execute(f"PRAGMA table_info({table})").fetchall()
    return [(row[1], row[2], row[3], row[5]) for row in rows]


def test_schema_creates_the_four_records(
    database: sqlite3.Connection,
) -> None:
    tables = sorted(
        row[0]
        for row in database.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
            " AND name NOT LIKE 'sqlite_%'"
        )
    )
    indexes = sorted(
        row[0]
        for row in database.execute(
            "SELECT name FROM sqlite_master WHERE type = 'index'"
            " AND name NOT LIKE 'sqlite_%'"
        )
    )

    assert tables == [
        "operation_results",
        "product_configuration",
        "schema_version",
        "tasks",
    ]
    assert len(indexes) == 2


def test_tasks_columns_match_the_design(
    database: sqlite3.Connection,
) -> None:
    assert column_shape(database, "tasks") == [
        ("task_id", "TEXT", 1, 1),
        ("title", "TEXT", 1, 0),
        ("title_key", "TEXT", 1, 0),
        ("observations", "TEXT", 0, 0),
        ("deadline_date", "TEXT", 0, 0),
        ("status", "TEXT", 1, 0),
        ("created_at_us", "INTEGER", 1, 0),
        ("latest_completed_at_us", "INTEGER", 0, 0),
        ("is_deleted", "INTEGER", 1, 0),
    ]


def test_operation_results_columns_match_the_design(
    database: sqlite3.Connection,
) -> None:
    assert column_shape(database, "operation_results") == [
        ("operation_id", "TEXT", 1, 1),
        ("canonical_request", "TEXT", 1, 0),
        ("outcome", "TEXT", 1, 0),
        ("http_status", "INTEGER", 1, 0),
        ("serialized_result", "TEXT", 1, 0),
        ("resolved_at_us", "INTEGER", 1, 0),
    ]


def test_operation_results_has_no_task_foreign_key(
    database: sqlite3.Connection,
) -> None:
    foreign_keys = database.execute(
        "PRAGMA foreign_key_list(operation_results)"
    ).fetchall()

    assert foreign_keys == []


def test_schema_version_records_version_one_as_a_singleton(
    database: sqlite3.Connection,
) -> None:
    rows = database.execute(
        "SELECT schema_version_id, version FROM schema_version"
    ).fetchall()

    assert rows == [(1, 1)]
    with pytest.raises(
        sqlite3.IntegrityError, match="CHECK constraint failed"
    ):
        database.execute(
            "INSERT INTO schema_version (schema_version_id, version)"
            " VALUES (2, 2)"
        )


def test_product_configuration_is_a_singleton_with_a_required_zone(
    database: sqlite3.Connection,
) -> None:
    database.execute(
        "INSERT INTO product_configuration"
        " (configuration_id, product_time_zone) VALUES (1, ?)",
        ("America/Sao_Paulo",),
    )

    with pytest.raises(
        sqlite3.IntegrityError, match="CHECK constraint failed"
    ):
        database.execute(
            "INSERT INTO product_configuration"
            " (configuration_id, product_time_zone) VALUES (2, ?)",
            ("UTC",),
        )
    with pytest.raises(
        sqlite3.IntegrityError, match="NOT NULL constraint failed"
    ):
        database.execute(
            "INSERT INTO product_configuration"
            " (configuration_id, product_time_zone) VALUES (1, NULL)"
        )


def test_duplicate_dated_title_and_deadline_is_rejected(
    database: sqlite3.Connection,
) -> None:
    insert_task(
        database,
        "task-1",
        "pay the electricity bill",
        deadline_date="2026-09-14",
    )

    with pytest.raises(
        sqlite3.IntegrityError,
        match=r"UNIQUE constraint failed: tasks\.title_key,"
        r" tasks\.deadline_date",
    ):
        insert_task(
            database,
            "task-2",
            "pay the electricity bill",
            deadline_date="2026-09-14",
        )


def test_dated_uniqueness_applies_irrespective_of_status(
    database: sqlite3.Connection,
) -> None:
    insert_task(
        database,
        "task-1",
        "pay the electricity bill",
        deadline_date="2026-09-14",
        status="completed",
        latest_completed_at_us=CREATED_AT_US + 1,
    )

    with pytest.raises(
        sqlite3.IntegrityError, match="UNIQUE constraint failed"
    ):
        insert_task(
            database,
            "task-2",
            "pay the electricity bill",
            deadline_date="2026-09-14",
        )


def test_equivalent_titles_with_different_deadlines_coexist(
    database: sqlite3.Connection,
) -> None:
    insert_task(
        database,
        "task-1",
        "pay the electricity bill",
        deadline_date="2026-09-14",
    )
    insert_task(
        database,
        "task-2",
        "pay the electricity bill",
        deadline_date="2026-09-15",
    )

    stored = database.execute("SELECT COUNT(*) FROM tasks").fetchone()

    assert stored == (2,)


def test_duplicate_undated_pending_title_is_rejected(
    database: sqlite3.Connection,
) -> None:
    insert_task(database, "task-1", "pay the electricity bill")

    with pytest.raises(
        sqlite3.IntegrityError,
        match=r"UNIQUE constraint failed: tasks\.title_key$",
    ):
        insert_task(database, "task-2", "pay the electricity bill")


def test_completed_undated_duplicate_title_is_allowed(
    database: sqlite3.Connection,
) -> None:
    insert_task(
        database,
        "task-1",
        "pay the electricity bill",
        status="completed",
        latest_completed_at_us=CREATED_AT_US + 1,
    )
    insert_task(database, "task-2", "pay the electricity bill")

    stored = database.execute("SELECT COUNT(*) FROM tasks").fetchone()

    assert stored == (2,)


def test_undated_and_dated_tasks_with_one_title_coexist(
    database: sqlite3.Connection,
) -> None:
    insert_task(database, "task-1", "pay the electricity bill")
    insert_task(
        database,
        "task-2",
        "pay the electricity bill",
        deadline_date="2026-09-14",
    )

    stored = database.execute("SELECT COUNT(*) FROM tasks").fetchone()

    assert stored == (2,)


def test_deleted_dated_task_is_excluded_from_uniqueness(
    database: sqlite3.Connection,
) -> None:
    insert_task(
        database,
        "task-1",
        "pay the electricity bill",
        deadline_date="2026-09-14",
        is_deleted=1,
    )
    insert_task(
        database,
        "task-2",
        "pay the electricity bill",
        deadline_date="2026-09-14",
    )

    live = database.execute(
        "SELECT COUNT(*) FROM tasks WHERE is_deleted = 0"
    ).fetchone()

    assert live == (1,)


def test_deleted_undated_pending_task_is_excluded_from_uniqueness(
    database: sqlite3.Connection,
) -> None:
    insert_task(database, "task-1", "pay the electricity bill", is_deleted=1)
    insert_task(database, "task-2", "pay the electricity bill")

    live = database.execute(
        "SELECT COUNT(*) FROM tasks WHERE is_deleted = 0"
    ).fetchone()

    assert live == (1,)


def test_invalid_status_is_rejected(
    database: sqlite3.Connection,
) -> None:
    with pytest.raises(
        sqlite3.IntegrityError, match="CHECK constraint failed"
    ):
        insert_task(
            database, "task-1", "pay the electricity bill", status="archived"
        )


def test_invalid_is_deleted_is_rejected(
    database: sqlite3.Connection,
) -> None:
    with pytest.raises(
        sqlite3.IntegrityError, match="CHECK constraint failed"
    ):
        insert_task(
            database, "task-1", "pay the electricity bill", is_deleted=2
        )


def test_title_key_comparison_is_binary(
    database: sqlite3.Connection,
) -> None:
    insert_task(database, "task-1", "pay the electricity bill")
    insert_task(database, "task-2", "Pay The Electricity Bill")

    stored = database.execute("SELECT COUNT(*) FROM tasks").fetchone()

    assert stored == (2,)

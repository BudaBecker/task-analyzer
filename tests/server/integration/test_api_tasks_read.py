"""End-to-end tests for reading the managed task collection.

Covers PCE-30, PCE-36; REQ-010, REQ-028.

Every test composes the real application against a newly allocated
temporary database created by the explicit initializer, so no test
reaches any configured runtime database.

Array order is deliberately never asserted: the approved contract does
not make it a product guarantee, so the tests compare collections.
"""

from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from task_analyzer_server import app as app_module
from task_analyzer_server import schema, services, storage
from task_analyzer_server.contracts import OperationRequest
from task_analyzer_server.settings import ServerSettings

BUSY_TIMEOUT_MS = 5000

PRODUCT_ZONE = "America/Sao_Paulo"

SERVER_NOW = datetime(2026, 9, 14, 2, 30, 0, 123456, tzinfo=UTC)
SERVER_NOW_TEXT = "2026-09-14T02:30:00.123456Z"
PRODUCT_DATE_IN_SAO_PAULO = "2026-09-13"

LATER_NOW = datetime(2026, 9, 16, 5, 0, 0, 0, tzinfo=UTC)

TASK_TARGET = "/v1/tasks"
TASKS_ROUTE = "/v1/tasks"

FIRST_TITLE = "Read notes"
SECOND_TITLE = "Review the draft"
DELETED_TITLE = "Already removed"
DEADLINE = "2026-09-14"

TASK_LIST_FIELDS = frozenset(
    {"items", "product_time_zone", "server_now", "product_date"}
)
TASK_SNAPSHOT_FIELDS = frozenset(
    {
        "task_id",
        "title",
        "observations",
        "deadline",
        "status",
        "created_at",
        "completed_at",
    }
)

INSERT_DELETED_TASK = (
    "INSERT INTO tasks ("
    " task_id, title, title_key, observations, deadline_date,"
    " status, created_at_us, latest_completed_at_us, is_deleted"
    ") VALUES (?, ?, ?, NULL, NULL, 'pending', 0, NULL, 1)"
)


class FixedClock:
    """A clock reporting one instant, in one representation."""

    def __init__(self, instant: datetime = SERVER_NOW) -> None:
        """Build the clock.

        Args:
            instant: The instant every reading returns.
        """
        self.instant = instant

    def now(self) -> datetime:
        """Read the fixed instant.

        Returns:
            The instant this clock was built with.
        """
        return self.instant


class AdvancingClock:
    """A clock whose every reading lands on a different product date."""

    def __init__(self, instants: list[datetime]) -> None:
        """Build the clock.

        Args:
            instants: The instants to report, one per reading. The last
                one repeats once the list is exhausted.
        """
        self.instants = instants
        self.readings = 0

    def now(self) -> datetime:
        """Read the next instant.

        Returns:
            The instant for this reading.
        """
        index = min(self.readings, len(self.instants) - 1)
        self.readings += 1
        return self.instants[index]


@pytest.fixture
def settings(tmp_path: Path) -> ServerSettings:
    """Build settings for a disposable initialized database.

    Args:
        tmp_path: pytest-allocated temporary directory.

    Returns:
        Settings naming the newly created database file.
    """
    path = tmp_path / "disposable.sqlite3"
    schema.initialize_database(path)
    return ServerSettings(
        database_path=path,
        log_level="INFO",
        db_busy_timeout_ms=BUSY_TIMEOUT_MS,
    )


@pytest.fixture
def configured(settings: ServerSettings) -> ServerSettings:
    """Fix the product zone on the disposable database.

    Args:
        settings: Settings naming the disposable database.

    Returns:
        The same settings, with the zone now fixed.
    """
    services.configure_zone(settings, FixedClock(), PRODUCT_ZONE)
    return settings


@pytest.fixture
def composed(settings: ServerSettings) -> FastAPI:
    """Compose the real application for the disposable database.

    Args:
        settings: Settings naming the disposable database.

    Returns:
        The composed application, not yet started.
    """
    return app_module.create_app(settings, FixedClock())


def create(settings: ServerSettings, payload: object) -> UUID:
    """Create one task and return the identity it was stored under.

    Args:
        settings: Settings naming the disposable database.
        payload: The submitted task payload.

    Returns:
        The identity of the created task.

    Raises:
        AssertionError: If the creation was not accepted, which would
            make the test's premise untrue.
    """
    result = services.create_task(
        settings,
        FixedClock(),
        OperationRequest(
            operation_id=uuid4(),
            method="POST",
            target=TASK_TARGET,
            payload=payload,
        ),
    )
    assert result.task is not None
    return result.task.task_id


def insert_deleted_task(settings: ServerSettings, title: str) -> UUID:
    """Store one task already excluded from the managed collection.

    Args:
        settings: Settings naming the disposable database.
        title: Title of the excluded task.

    Returns:
        The identity of the excluded task.
    """
    task_id = uuid4()
    with storage.open_connection(
        settings.database_path, BUSY_TIMEOUT_MS
    ) as connection:
        with storage.write_transaction(connection):
            connection.execute(
                INSERT_DELETED_TASK, (str(task_id), title, title)
            )
    return task_id


def test_an_empty_collection_is_an_empty_array(
    composed: FastAPI, configured: ServerSettings
) -> None:
    """Nothing managed reads as an empty array, never as an absence."""
    with TestClient(composed) as client:
        response = client.get(TASKS_ROUTE)
    body = response.json()

    assert response.status_code == 200
    assert body["items"] == []


def test_an_empty_collection_still_carries_its_time_context(
    composed: FastAPI, configured: ServerSettings
) -> None:
    """An empty reading still reports the zone and the sampled time."""
    with TestClient(composed) as client:
        body = client.get(TASKS_ROUTE).json()

    assert body["product_time_zone"] == PRODUCT_ZONE
    assert body["server_now"] == SERVER_NOW_TEXT
    assert body["product_date"] == PRODUCT_DATE_IN_SAO_PAULO


def test_an_unconfigured_server_reports_no_zone_or_product_date(
    composed: FastAPI,
) -> None:
    """Before setup the reading reports the absence of a zone."""
    with TestClient(composed) as client:
        body = client.get(TASKS_ROUTE).json()

    assert body["items"] == []
    assert body["product_time_zone"] is None
    assert body["product_date"] is None


def test_a_populated_collection_reports_every_managed_task(
    composed: FastAPI, configured: ServerSettings
) -> None:
    """Every created task is read back, in no guaranteed order."""
    first = create(configured, {"title": FIRST_TITLE})
    second = create(configured, {"title": SECOND_TITLE})

    with TestClient(composed) as client:
        body = client.get(TASKS_ROUTE).json()

    assert {item["task_id"] for item in body["items"]} == {
        str(first),
        str(second),
    }
    assert {item["title"] for item in body["items"]} == {
        FIRST_TITLE,
        SECOND_TITLE,
    }


def test_a_task_is_published_with_exactly_its_approved_fields(
    composed: FastAPI, configured: ServerSettings
) -> None:
    """A snapshot carries the approved fields and no internal ones."""
    create(
        configured,
        {
            "title": FIRST_TITLE,
            "observations": "line one\nline two",
            "deadline": DEADLINE,
        },
    )

    with TestClient(composed) as client:
        body = client.get(TASKS_ROUTE).json()
    item = body["items"][0]

    assert set(item) == TASK_SNAPSHOT_FIELDS
    assert item["observations"] == "line one\nline two"
    assert item["deadline"] == DEADLINE
    assert item["status"] == "pending"
    assert item["completed_at"] is None


def test_a_deleted_task_is_excluded_from_the_reading(
    composed: FastAPI, configured: ServerSettings
) -> None:
    """A task outside the managed collection is not read back."""
    kept = create(configured, {"title": FIRST_TITLE})
    removed = insert_deleted_task(configured, DELETED_TITLE)

    with TestClient(composed) as client:
        body = client.get(TASKS_ROUTE).json()

    assert {item["task_id"] for item in body["items"]} == {str(kept)}
    assert str(removed) not in {item["task_id"] for item in body["items"]}


def test_the_reading_publishes_exactly_its_approved_fields(
    composed: FastAPI, configured: ServerSettings
) -> None:
    """No sorting, paging, emphasis or metric field is published."""
    create(configured, {"title": FIRST_TITLE})

    with TestClient(composed) as client:
        body = client.get(TASKS_ROUTE).json()

    assert set(body) == TASK_LIST_FIELDS


def test_one_reading_uses_one_sampled_server_time(
    settings: ServerSettings,
) -> None:
    """The published date belongs to the published instant."""
    services.configure_zone(settings, FixedClock(), PRODUCT_ZONE)
    composed = app_module.create_app(
        settings, AdvancingClock([SERVER_NOW, LATER_NOW])
    )

    with TestClient(composed) as client:
        body = client.get(TASKS_ROUTE).json()

    assert body["server_now"] == SERVER_NOW_TEXT
    assert body["product_date"] == PRODUCT_DATE_IN_SAO_PAULO


def test_the_reading_uses_a_fresh_committed_snapshot(
    composed: FastAPI, configured: ServerSettings
) -> None:
    """A task committed after startup is read back immediately."""
    with TestClient(composed) as client:
        before = client.get(TASKS_ROUTE).json()
        created = create(configured, {"title": FIRST_TITLE})
        after = client.get(TASKS_ROUTE).json()

    assert before["items"] == []
    assert {item["task_id"] for item in after["items"]} == {str(created)}


def test_the_reading_is_not_cacheable(
    composed: FastAPI, configured: ServerSettings
) -> None:
    """A task reading always reaches the server."""
    with TestClient(composed) as client:
        response = client.get(TASKS_ROUTE)

    assert response.headers["Cache-Control"] == "no-store"

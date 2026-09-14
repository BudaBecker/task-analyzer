"""End-to-end tests for reading the managed task collection.

Covers PCE-30, PCE-36; REQ-010, REQ-028.
"""

from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from helpers import FixedClock

from task_analyzer_server import app as app_module
from task_analyzer_server import services, storage
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


class AdvancingClock:
    def __init__(self, instants: list[datetime]) -> None:
        self.instants = instants
        self.readings = 0

    def now(self) -> datetime:
        index = min(self.readings, len(self.instants) - 1)
        self.readings += 1
        return self.instants[index]


@pytest.fixture
def configured(settings: ServerSettings) -> ServerSettings:
    services.configure_zone(settings, FixedClock(SERVER_NOW), PRODUCT_ZONE)
    return settings


@pytest.fixture
def composed(settings: ServerSettings) -> FastAPI:
    return app_module.create_app(settings, FixedClock(SERVER_NOW))


def create(settings: ServerSettings, payload: object) -> UUID:
    result = services.create_task(
        settings,
        FixedClock(SERVER_NOW),
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
    with TestClient(composed) as client:
        response = client.get(TASKS_ROUTE)
    body = response.json()

    assert response.status_code == 200
    assert body["items"] == []


def test_an_empty_collection_still_carries_its_time_context(
    composed: FastAPI, configured: ServerSettings
) -> None:
    with TestClient(composed) as client:
        body = client.get(TASKS_ROUTE).json()

    assert body["product_time_zone"] == PRODUCT_ZONE
    assert body["server_now"] == SERVER_NOW_TEXT
    assert body["product_date"] == PRODUCT_DATE_IN_SAO_PAULO


def test_an_unconfigured_server_reports_no_zone_or_product_date(
    composed: FastAPI,
) -> None:
    with TestClient(composed) as client:
        body = client.get(TASKS_ROUTE).json()

    assert body["items"] == []
    assert body["product_time_zone"] is None
    assert body["product_date"] is None


def test_a_populated_collection_reports_every_managed_task(
    composed: FastAPI, configured: ServerSettings
) -> None:
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
    kept = create(configured, {"title": FIRST_TITLE})
    removed = insert_deleted_task(configured, DELETED_TITLE)

    with TestClient(composed) as client:
        body = client.get(TASKS_ROUTE).json()

    assert {item["task_id"] for item in body["items"]} == {str(kept)}
    assert str(removed) not in {item["task_id"] for item in body["items"]}


def test_the_reading_publishes_exactly_its_approved_fields(
    composed: FastAPI, configured: ServerSettings
) -> None:
    create(configured, {"title": FIRST_TITLE})

    with TestClient(composed) as client:
        body = client.get(TASKS_ROUTE).json()

    assert set(body) == TASK_LIST_FIELDS


def test_one_reading_uses_one_sampled_server_time(
    settings: ServerSettings,
) -> None:
    services.configure_zone(settings, FixedClock(SERVER_NOW), PRODUCT_ZONE)
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
    with TestClient(composed) as client:
        before = client.get(TASKS_ROUTE).json()
        created = create(configured, {"title": FIRST_TITLE})
        after = client.get(TASKS_ROUTE).json()

    assert before["items"] == []
    assert {item["task_id"] for item in after["items"]} == {str(created)}


def test_the_reading_is_not_cacheable(
    composed: FastAPI, configured: ServerSettings
) -> None:
    with TestClient(composed) as client:
        response = client.get(TASKS_ROUTE)

    assert response.headers["Cache-Control"] == "no-store"

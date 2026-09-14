"""End-to-end tests for consulting an operation's outcome.

Covers PCE-26, PCE-38, PCE-40, PCE-41, PCE-42, PCE-43; REQ-010,
REQ-029, REQ-031.

Every test composes the real application against a newly allocated
temporary database created by the explicit initializer, so no test
reaches any configured runtime database.

The outcomes consulted here are established by the real services, so
each assertion is about what the server actually retained rather than
about a fixture written straight into the ledger.
"""

from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from task_analyzer_server import app as app_module
from task_analyzer_server import schema, services, storage
from task_analyzer_server.contracts import (
    ErrorCode,
    FieldErrorCode,
    OperationRequest,
)
from task_analyzer_server.settings import ServerSettings

BUSY_TIMEOUT_MS = 5000

PRODUCT_ZONE = "America/Sao_Paulo"
SERVER_NOW = datetime(2026, 9, 14, 12, 0, 0, 123456, tzinfo=UTC)

TASK_TITLE = "Read notes"
DEADLINE = "2026-09-14"
TASK_TARGET = "/v1/tasks"

UNKNOWN_OPERATION_ID = UUID("10000000-0000-4000-8000-000000000009")

PROTOCOL_ERROR_FIELDS_WITH_OPERATION = frozenset(
    {"request_id", "error", "operation_id"}
)
OPERATION_RESULT_FIELDS = frozenset(
    {
        "operation_id",
        "outcome",
        "original_http_status",
        "task",
        "error",
        "resolved_at",
    }
)

COUNT_TASKS = "SELECT COUNT(*) FROM tasks WHERE is_deleted = 0"


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


@pytest.fixture
def settings(tmp_path: Path) -> ServerSettings:
    """Build settings for a disposable configured database.

    Args:
        tmp_path: pytest-allocated temporary directory.

    Returns:
        Settings naming the newly created database file.
    """
    path = tmp_path / "disposable.sqlite3"
    schema.initialize_database(path)
    built = ServerSettings(
        database_path=path,
        log_level="INFO",
        db_busy_timeout_ms=BUSY_TIMEOUT_MS,
    )
    services.configure_zone(built, FixedClock(), PRODUCT_ZONE)
    return built


@pytest.fixture
def composed(settings: ServerSettings) -> FastAPI:
    """Compose the real application for the disposable database.

    Args:
        settings: Settings naming the disposable database.

    Returns:
        The composed application, not yet started.
    """
    return app_module.create_app(settings, FixedClock())


def create(
    settings: ServerSettings,
    payload: object,
    operation_id: UUID | None = None,
) -> UUID:
    """Resolve one creation attempt and return its identity.

    Args:
        settings: Settings naming the disposable database.
        payload: The submitted task payload.
        operation_id: Identity to submit, generated when omitted.

    Returns:
        The identity of the resolved operation.
    """
    identity = uuid4() if operation_id is None else operation_id
    services.create_task(
        settings,
        FixedClock(),
        OperationRequest(
            operation_id=identity,
            method="POST",
            target=TASK_TARGET,
            payload=payload,
        ),
    )
    return identity


def managed_tasks(settings: ServerSettings) -> int:
    """Count the managed tasks through a separate new connection.

    Args:
        settings: Settings naming the disposable database.

    Returns:
        How many non-deleted tasks are stored.
    """
    with storage.open_connection(
        settings.database_path, BUSY_TIMEOUT_MS
    ) as connection:
        return int(connection.execute(COUNT_TASKS).fetchone()[0])


def test_a_stored_success_is_published_with_status_200(
    composed: FastAPI, settings: ServerSettings
) -> None:
    """Consulting an established outcome answers with 200."""
    identity = create(settings, {"title": TASK_TITLE})

    with TestClient(composed) as client:
        response = client.get(f"/v1/operations/{identity}")

    assert response.status_code == 200


def test_a_stored_success_keeps_its_original_status_inside_the_result(
    composed: FastAPI, settings: ServerSettings
) -> None:
    """The creation's own 201 survives inside the consulted result."""
    identity = create(settings, {"title": TASK_TITLE})

    with TestClient(composed) as client:
        body = client.get(f"/v1/operations/{identity}").json()

    assert body["outcome"] == "succeeded"
    assert body["original_http_status"] == 201


def test_a_stored_success_publishes_the_created_task_snapshot(
    composed: FastAPI, settings: ServerSettings
) -> None:
    """The consulted result carries the task exactly as created."""
    identity = create(settings, {"title": TASK_TITLE, "deadline": DEADLINE})

    with TestClient(composed) as client:
        body = client.get(f"/v1/operations/{identity}").json()

    assert body["task"]["title"] == TASK_TITLE
    assert body["task"]["deadline"] == DEADLINE
    assert body["task"]["status"] == "pending"
    assert body["task"]["created_at"] == "2026-09-14T12:00:00.123456Z"


def test_a_stored_success_publishes_exactly_the_result_fields(
    composed: FastAPI, settings: ServerSettings
) -> None:
    """The published result carries the approved fields and no others."""
    identity = create(settings, {"title": TASK_TITLE})

    with TestClient(composed) as client:
        body = client.get(f"/v1/operations/{identity}").json()

    assert set(body) == OPERATION_RESULT_FIELDS
    assert body["operation_id"] == str(identity)


def test_a_stored_rejection_is_also_published_with_status_200(
    composed: FastAPI, settings: ServerSettings
) -> None:
    """A rejection is an established outcome, so consulting it is 200."""
    identity = create(settings, {"title": ""})

    with TestClient(composed) as client:
        response = client.get(f"/v1/operations/{identity}")

    assert response.status_code == 200
    assert response.json()["outcome"] == "rejected"


def test_a_consulted_rejection_keeps_its_own_original_status(
    composed: FastAPI, settings: ServerSettings
) -> None:
    """Consulting at 200 never overrides the rejection's own status."""
    identity = create(settings, {"title": ""})

    with TestClient(composed) as client:
        body = client.get(f"/v1/operations/{identity}").json()

    assert body["original_http_status"] == 422
    assert body["error"]["code"] == ErrorCode.TASK_VALIDATION_FAILED.value
    assert body["error"]["fields"] == [
        {"field": "title", "code": FieldErrorCode.TITLE_REQUIRED.value}
    ]


def test_consulting_status_200_is_not_evidence_of_persistence(
    composed: FastAPI, settings: ServerSettings
) -> None:
    """A 200 consultation of a rejection persisted no task at all."""
    identity = create(settings, {"title": ""})

    with TestClient(composed) as client:
        response = client.get(f"/v1/operations/{identity}")

    assert response.status_code == 200
    assert response.json()["task"] is None
    assert managed_tasks(settings) == 0


def test_a_uniqueness_rejection_names_the_conflicting_task(
    composed: FastAPI, settings: ServerSettings
) -> None:
    """A consulted uniqueness rejection identifies the conflict."""
    first = create(settings, {"title": TASK_TITLE, "deadline": DEADLINE})
    second = create(settings, {"title": TASK_TITLE, "deadline": DEADLINE})

    with TestClient(composed) as client:
        original = client.get(f"/v1/operations/{first}").json()
        conflict = client.get(f"/v1/operations/{second}").json()

    assert conflict["outcome"] == "rejected"
    assert conflict["original_http_status"] == 409
    assert (
        conflict["error"]["code"] == ErrorCode.TASK_UNIQUENESS_CONFLICT.value
    )
    assert (
        conflict["error"]["conflicting_task_id"] == original["task"]["task_id"]
    )


def test_an_unestablished_outcome_is_unknown(composed: FastAPI) -> None:
    """No committed result answers 404 with the unknown code."""
    with TestClient(composed) as client:
        response = client.get(f"/v1/operations/{UNKNOWN_OPERATION_ID}")

    assert response.status_code == 404
    assert (
        response.json()["error"]["code"]
        == ErrorCode.OPERATION_RESULT_UNKNOWN.value
    )


def test_an_unknown_outcome_claims_no_rejection_or_rollback(
    composed: FastAPI,
) -> None:
    """Unknown carries no terminal outcome and no task of its own."""
    with TestClient(composed) as client:
        body = client.get(f"/v1/operations/{UNKNOWN_OPERATION_ID}").json()

    assert set(body) == PROTOCOL_ERROR_FIELDS_WITH_OPERATION
    assert body["operation_id"] == str(UNKNOWN_OPERATION_ID)
    assert UUID(body["request_id"])


def test_an_unusable_identity_is_refused_before_any_lookup(
    composed: FastAPI,
) -> None:
    """An unusable identity is an envelope failure, not an unknown one."""
    with TestClient(composed) as client:
        response = client.get("/v1/operations/1234")
    body = response.json()

    assert response.status_code == 400
    assert body["error"]["code"] == ErrorCode.INVALID_OPERATION_ENVELOPE.value
    assert "operation_id" not in body


def test_a_consulted_result_is_not_cacheable(
    composed: FastAPI, settings: ServerSettings
) -> None:
    """A consultation always reaches the server."""
    identity = create(settings, {"title": TASK_TITLE})

    with TestClient(composed) as client:
        response = client.get(f"/v1/operations/{identity}")

    assert response.headers["Cache-Control"] == "no-store"


def test_a_consultation_reads_a_fresh_committed_snapshot(
    composed: FastAPI, settings: ServerSettings
) -> None:
    """An outcome established after startup is found immediately."""
    with TestClient(composed) as client:
        before = client.get(f"/v1/operations/{UNKNOWN_OPERATION_ID}")
        identity = create(
            settings, {"title": TASK_TITLE}, UNKNOWN_OPERATION_ID
        )
        after = client.get(f"/v1/operations/{identity}")

    assert before.status_code == 404
    assert after.status_code == 200
    assert after.json()["outcome"] == "succeeded"


def test_a_consultation_changes_no_task(
    composed: FastAPI, settings: ServerSettings
) -> None:
    """Consulting an outcome is a read and applies nothing again."""
    identity = create(settings, {"title": TASK_TITLE})

    with TestClient(composed) as client:
        first = client.get(f"/v1/operations/{identity}").json()
        second = client.get(f"/v1/operations/{identity}").json()

    assert first == second
    assert managed_tasks(settings) == 1

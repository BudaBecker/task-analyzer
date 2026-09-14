"""End-to-end tests for creating a task over HTTP.

Covers PCE-01 through PCE-10, PCE-19, PCE-20, PCE-26, PCE-37 through
PCE-40, PCE-48, PCE-51, PCE-52; REQ-007, REQ-010, REQ-029, REQ-031.

Every test composes the real application against a newly allocated
temporary database created by the explicit initializer, so no test
reaches any configured runtime database.

The suite keeps two failures apart throughout: a retained rejection,
which the server can still describe afterwards, and a protocol-only
failure, which registers nothing at all. Each case therefore checks the
response and then consults the operation identity.
"""

import logging
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from task_analyzer_server import api, schema, services
from task_analyzer_server import app as app_module
from task_analyzer_server.contracts import ErrorCode, FieldErrorCode
from task_analyzer_server.settings import ServerSettings

BUSY_TIMEOUT_MS = 5000

PRODUCT_ZONE = "America/Sao_Paulo"
SERVER_NOW = datetime(2026, 9, 14, 12, 0, 0, 123456, tzinfo=UTC)
CREATED_AT_TEXT = "2026-09-14T12:00:00.123456Z"

TASKS_ROUTE = "/v1/tasks"
OPERATIONS_ROUTE = "/v1/operations"

TASK_TITLE = "Read notes"
OTHER_TITLE = "Review the draft"
DEADLINE = "2026-09-14"

TITLE_AT_LIMIT = "t" * 200
TITLE_OVER_LIMIT = "t" * 201
OBSERVATIONS_AT_LIMIT = "o" * 5000
OBSERVATIONS_OVER_LIMIT = "o" * 5001

EARLIEST_DEADLINE = "0001-01-01"
LATEST_DEADLINE = "9999-12-30"
UNSUPPORTED_DEADLINE = "9999-12-31"

PROTOCOL_ERROR_FIELDS = frozenset({"request_id", "error"})


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
def database_path(tmp_path: Path) -> Path:
    """Allocate a disposable initialized database.

    Args:
        tmp_path: pytest-allocated temporary directory.

    Returns:
        Path of the newly created database file.
    """
    path = tmp_path / "disposable.sqlite3"
    schema.initialize_database(path)
    return path


@pytest.fixture
def settings(database_path: Path) -> ServerSettings:
    """Build settings naming the disposable database.

    Args:
        database_path: Path of the disposable database.

    Returns:
        Settings for that file.
    """
    return ServerSettings(
        database_path=database_path,
        log_level="INFO",
        db_busy_timeout_ms=BUSY_TIMEOUT_MS,
    )


@pytest.fixture
def unconfigured(settings: ServerSettings) -> FastAPI:
    """Compose the application before the product zone is fixed.

    Args:
        settings: Settings naming the disposable database.

    Returns:
        The composed application, not yet started.
    """
    return app_module.create_app(settings, FixedClock())


@pytest.fixture
def composed(settings: ServerSettings) -> FastAPI:
    """Compose the application with the product zone already fixed.

    Args:
        settings: Settings naming the disposable database.

    Returns:
        The composed application, not yet started.
    """
    services.configure_zone(settings, FixedClock(), PRODUCT_ZONE)
    return app_module.create_app(settings, FixedClock())


def submit(
    client: TestClient,
    payload: object,
    operation_id: UUID | None = None,
) -> tuple[UUID, dict[str, object]]:
    """Submit one creation attempt and return its identity and body.

    Args:
        client: The started test client.
        payload: The submitted task payload.
        operation_id: Identity to submit, generated when omitted.

    Returns:
        The submitted identity and the parsed response body.
    """
    identity = uuid4() if operation_id is None else operation_id
    response = client.post(
        TASKS_ROUTE,
        json=payload,
        headers={"Operation-Id": str(identity)},
    )
    return identity, {"status": response.status_code, **response.json()}


def resolved_records(
    caplog: pytest.LogCaptureFixture,
) -> list[logging.LogRecord]:
    """Collect the records describing a settled operation.

    Args:
        caplog: pytest's log capture fixture.

    Returns:
        Every captured operation-resolved record, in order.
    """
    return [
        record
        for record in caplog.records
        if record.getMessage() == api.OPERATION_RESOLVED_EVENT
    ]


def titles(client: TestClient) -> list[str]:
    """Read the titles of every managed task.

    Args:
        client: The started test client.

    Returns:
        The titles currently managed, in no guaranteed order.
    """
    body = client.get(TASKS_ROUTE).json()
    return [str(item["title"]) for item in body["items"]]


def test_a_valid_creation_is_accepted_with_status_201(
    composed: FastAPI,
) -> None:
    """An accepted creation answers with the created status."""
    with TestClient(composed) as client:
        identity, body = submit(client, {"title": TASK_TITLE})

    assert body["status"] == 201
    assert body["outcome"] == "succeeded"
    assert body["original_http_status"] == 201
    assert body["operation_id"] == str(identity)


def test_a_valid_creation_publishes_the_created_snapshot(
    composed: FastAPI,
) -> None:
    """The result carries the task exactly as it was stored."""
    with TestClient(composed) as client:
        _, body = submit(
            client,
            {
                "title": TASK_TITLE,
                "observations": "line one\nline two",
                "deadline": DEADLINE,
            },
        )
    task = body["task"]

    assert isinstance(task, dict)
    assert task["title"] == TASK_TITLE
    assert task["observations"] == "line one\nline two"
    assert task["deadline"] == DEADLINE
    assert task["status"] == "pending"
    assert task["created_at"] == CREATED_AT_TEXT
    assert task["completed_at"] is None


def test_an_accepted_creation_is_persisted(composed: FastAPI) -> None:
    """The created task is part of the managed collection."""
    with TestClient(composed) as client:
        submit(client, {"title": TASK_TITLE})

        assert titles(client) == [TASK_TITLE]


def test_omitted_optional_fields_are_stored_as_absent(
    composed: FastAPI,
) -> None:
    """A creation without optional values stores none."""
    with TestClient(composed) as client:
        _, body = submit(client, {"title": TASK_TITLE})
    task = body["task"]

    assert isinstance(task, dict)
    assert task["observations"] is None
    assert task["deadline"] is None


def test_a_title_at_the_limit_is_accepted(composed: FastAPI) -> None:
    """A 200-character title is inside the approved bound."""
    with TestClient(composed) as client:
        _, body = submit(client, {"title": TITLE_AT_LIMIT})

    assert body["status"] == 201
    assert body["outcome"] == "succeeded"


def test_a_title_over_the_limit_is_rejected(composed: FastAPI) -> None:
    """A 201-character title is outside the approved bound."""
    with TestClient(composed) as client:
        _, body = submit(client, {"title": TITLE_OVER_LIMIT})
    error = body["error"]

    assert body["status"] == 422
    assert body["outcome"] == "rejected"
    assert isinstance(error, dict)
    assert error["code"] == ErrorCode.TASK_VALIDATION_FAILED.value
    assert error["fields"] == [
        {"field": "title", "code": FieldErrorCode.TITLE_TOO_LONG.value}
    ]


def test_observations_at_the_limit_are_accepted(composed: FastAPI) -> None:
    """5,000 observation characters are inside the approved bound."""
    with TestClient(composed) as client:
        _, body = submit(
            client,
            {
                "title": TASK_TITLE,
                "observations": OBSERVATIONS_AT_LIMIT,
            },
        )

    assert body["status"] == 201
    assert body["outcome"] == "succeeded"


def test_observations_over_the_limit_are_rejected(
    composed: FastAPI,
) -> None:
    """5,001 observation characters are outside the approved bound."""
    with TestClient(composed) as client:
        _, body = submit(
            client,
            {
                "title": TASK_TITLE,
                "observations": OBSERVATIONS_OVER_LIMIT,
            },
        )
    error = body["error"]

    assert body["status"] == 422
    assert isinstance(error, dict)
    assert error["fields"] == [
        {
            "field": "observations",
            "code": FieldErrorCode.OBSERVATIONS_TOO_LONG.value,
        }
    ]


def test_the_supported_deadline_endpoints_are_accepted(
    composed: FastAPI,
) -> None:
    """Both ends of the approved deadline range are usable."""
    with TestClient(composed) as client:
        _, earliest = submit(
            client, {"title": TASK_TITLE, "deadline": EARLIEST_DEADLINE}
        )
        _, latest = submit(
            client, {"title": OTHER_TITLE, "deadline": LATEST_DEADLINE}
        )

    assert earliest["status"] == 201
    assert latest["status"] == 201


def test_a_deadline_outside_the_supported_range_is_rejected(
    composed: FastAPI,
) -> None:
    """A deadline past the approved range changes no task state."""
    with TestClient(composed) as client:
        _, body = submit(
            client,
            {"title": TASK_TITLE, "deadline": UNSUPPORTED_DEADLINE},
        )

        assert titles(client) == []
    error = body["error"]

    assert body["status"] == 422
    assert isinstance(error, dict)
    assert error["fields"] == [
        {"field": "deadline", "code": FieldErrorCode.INVALID_DEADLINE.value}
    ]


def test_a_wrong_field_type_is_a_retained_rejection(
    composed: FastAPI,
) -> None:
    """A type the contract refuses is decided inside the flow."""
    with TestClient(composed) as client:
        identity, body = submit(client, {"title": 7})
        consulted = client.get(f"{OPERATIONS_ROUTE}/{identity}")
    error = body["error"]

    assert body["status"] == 422
    assert isinstance(error, dict)
    assert error["fields"] == [
        {"field": "title", "code": FieldErrorCode.INVALID_FIELD_TYPE.value}
    ]
    assert consulted.status_code == 200
    assert consulted.json()["outcome"] == "rejected"


def test_an_unknown_field_is_a_retained_rejection(
    composed: FastAPI,
) -> None:
    """A field the contract does not define is rejected durably."""
    with TestClient(composed) as client:
        identity, body = submit(
            client, {"title": TASK_TITLE, "status": "completed"}
        )
        consulted = client.get(f"{OPERATIONS_ROUTE}/{identity}")
    error = body["error"]

    assert body["status"] == 422
    assert isinstance(error, dict)
    assert error["fields"] == [
        {"field": "status", "code": FieldErrorCode.UNEXPECTED_FIELD.value}
    ]
    assert consulted.json()["error"]["fields"] == error["fields"]


def test_a_validation_rejection_creates_no_task(
    composed: FastAPI,
) -> None:
    """A rejected submission leaves the collection untouched."""
    with TestClient(composed) as client:
        _, body = submit(client, {"title": ""})

        assert titles(client) == []
    error = body["error"]

    assert isinstance(error, dict)
    assert error["fields"] == [
        {"field": "title", "code": FieldErrorCode.TITLE_REQUIRED.value}
    ]


def test_a_uniqueness_conflict_is_rejected_with_status_409(
    composed: FastAPI,
) -> None:
    """A second task with the same title and date is refused."""
    with TestClient(composed) as client:
        _, first = submit(client, {"title": TASK_TITLE, "deadline": DEADLINE})
        _, second = submit(client, {"title": TASK_TITLE, "deadline": DEADLINE})
    original = first["task"]
    error = second["error"]

    assert second["status"] == 409
    assert second["outcome"] == "rejected"
    assert isinstance(original, dict)
    assert isinstance(error, dict)
    assert error["code"] == ErrorCode.TASK_UNIQUENESS_CONFLICT.value
    assert error["conflicting_task_id"] == original["task_id"]


def test_a_uniqueness_rejection_leaves_both_tasks_unchanged(
    composed: FastAPI,
) -> None:
    """The conflict creates nothing and changes nothing."""
    with TestClient(composed) as client:
        submit(client, {"title": TASK_TITLE, "deadline": DEADLINE})
        submit(client, {"title": TASK_TITLE, "deadline": DEADLINE})

        assert titles(client) == [TASK_TITLE]


def test_a_repeated_attempt_returns_the_original_result(
    composed: FastAPI,
) -> None:
    """A lost response is recovered by repeating the same attempt."""
    identity = uuid4()

    with TestClient(composed) as client:
        _, first = submit(client, {"title": TASK_TITLE}, identity)
        _, repeated = submit(client, {"title": TASK_TITLE}, identity)

    assert repeated["status"] == 201
    assert repeated == first


def test_a_repeated_attempt_creates_no_second_task(
    composed: FastAPI,
) -> None:
    """Repeating one attempt applies it once."""
    identity = uuid4()

    with TestClient(composed) as client:
        submit(client, {"title": TASK_TITLE}, identity)
        submit(client, {"title": TASK_TITLE}, identity)

        assert titles(client) == [TASK_TITLE]


def test_a_persisted_outcome_is_available_after_a_lost_response(
    composed: FastAPI,
) -> None:
    """Consulting the identity recovers the original outcome."""
    with TestClient(composed) as client:
        identity, original = submit(client, {"title": TASK_TITLE})
        consulted = client.get(f"{OPERATIONS_ROUTE}/{identity}")
    body = consulted.json()
    task = original["task"]

    assert consulted.status_code == 200
    assert isinstance(task, dict)
    assert body["task"]["task_id"] == task["task_id"]
    assert body["original_http_status"] == 201


def test_reusing_an_identity_for_other_content_is_refused(
    composed: FastAPI,
) -> None:
    """A different request under one identity is a protocol conflict."""
    identity = uuid4()

    with TestClient(composed) as client:
        _, first = submit(client, {"title": TASK_TITLE}, identity)
        response = client.post(
            TASKS_ROUTE,
            json={"title": OTHER_TITLE},
            headers={"Operation-Id": str(identity)},
        )
        consulted = client.get(f"{OPERATIONS_ROUTE}/{identity}").json()
    body = response.json()

    assert response.status_code == 409
    assert body["error"]["code"] == ErrorCode.OPERATION_ID_REUSED.value
    assert body["operation_id"] == str(identity)
    assert "outcome" not in body
    assert consulted["task"]["task_id"] == first["task"]["task_id"]


def test_reusing_an_identity_creates_no_second_task(
    composed: FastAPI,
) -> None:
    """The refused reuse leaves the original task alone."""
    identity = uuid4()

    with TestClient(composed) as client:
        submit(client, {"title": TASK_TITLE}, identity)
        client.post(
            TASKS_ROUTE,
            json={"title": OTHER_TITLE},
            headers={"Operation-Id": str(identity)},
        )

        assert titles(client) == [TASK_TITLE]


def test_an_unparseable_body_registers_no_outcome(
    composed: FastAPI,
) -> None:
    """Malformed JSON never enters the operation flow."""
    identity = uuid4()

    with TestClient(composed) as client:
        response = client.post(
            TASKS_ROUTE,
            content=b'{"title": ',
            headers={
                "Operation-Id": str(identity),
                "Content-Type": "application/json",
            },
        )
        consulted = client.get(f"{OPERATIONS_ROUTE}/{identity}")
    body = response.json()

    assert response.status_code == 400
    assert body["error"]["code"] == ErrorCode.INVALID_OPERATION_ENVELOPE.value
    assert consulted.status_code == 404
    assert (
        consulted.json()["error"]["code"]
        == ErrorCode.OPERATION_RESULT_UNKNOWN.value
    )


def test_an_unusable_operation_identity_is_refused(
    composed: FastAPI,
) -> None:
    """Without a usable identity the answer names no operation."""
    with TestClient(composed) as client:
        missing = client.post(TASKS_ROUTE, json={"title": TASK_TITLE})
        unusable = client.post(
            TASKS_ROUTE,
            json={"title": TASK_TITLE},
            headers={"Operation-Id": "not-a-uuid"},
        )

        assert titles(client) == []

    assert missing.status_code == 400
    assert set(missing.json()) == PROTOCOL_ERROR_FIELDS
    assert unusable.status_code == 400
    assert (
        unusable.json()["error"]["code"]
        == ErrorCode.INVALID_OPERATION_ENVELOPE.value
    )


def test_a_creation_before_zone_setup_is_refused(
    unconfigured: FastAPI,
) -> None:
    """A task command needs the product zone to be fixed first."""
    with TestClient(unconfigured) as client:
        identity = uuid4()
        response = client.post(
            TASKS_ROUTE,
            json={"title": TASK_TITLE},
            headers={"Operation-Id": str(identity)},
        )
        consulted = client.get(f"{OPERATIONS_ROUTE}/{identity}")
    body = response.json()

    assert response.status_code == 409
    assert body["error"]["code"] == ErrorCode.PRODUCT_TIME_ZONE_REQUIRED.value
    assert "outcome" not in body
    assert consulted.status_code == 404


def test_a_storage_failure_registers_no_outcome(
    composed: FastAPI, database_path: Path
) -> None:
    """An unavailable database confirms nothing and invents nothing."""
    identity = uuid4()

    with TestClient(composed) as client:
        database_path.unlink()
        response = client.post(
            TASKS_ROUTE,
            json={"title": TASK_TITLE},
            headers={"Operation-Id": str(identity)},
        )
    body = response.json()

    assert response.status_code == 503
    assert body["error"]["code"] == ErrorCode.STORAGE_UNAVAILABLE.value
    assert "outcome" not in body
    assert "task" not in body


def test_an_accepted_creation_is_recorded_after_it_is_persisted(
    composed: FastAPI, caplog: pytest.LogCaptureFixture
) -> None:
    """The success event names the operation and the stored task."""
    with caplog.at_level(logging.INFO, logger=api.__name__):
        with TestClient(composed) as client:
            identity, body = submit(client, {"title": TASK_TITLE})
            persisted = titles(client)
    task = body["task"]
    recorded = resolved_records(caplog)

    assert persisted == [TASK_TITLE]
    assert isinstance(task, dict)
    assert [record.outcome for record in recorded] == ["succeeded"]
    assert recorded[0].operation_id == str(identity)
    assert recorded[0].task_id == task["task_id"]
    assert recorded[0].duration_ms >= 0


def test_a_rejected_creation_is_recorded_without_a_task(
    composed: FastAPI, caplog: pytest.LogCaptureFixture
) -> None:
    """The rejection event names its code and no stored task."""
    with caplog.at_level(logging.INFO, logger=api.__name__):
        with TestClient(composed) as client:
            submit(client, {"title": ""})
    recorded = resolved_records(caplog)

    assert [record.outcome for record in recorded] == ["rejected"]
    assert recorded[0].error_code == (ErrorCode.TASK_VALIDATION_FAILED.value)
    assert recorded[0].task_id is None


def test_a_creation_response_is_not_cacheable(composed: FastAPI) -> None:
    """A creation answer always comes from the server."""
    with TestClient(composed) as client:
        response = client.post(
            TASKS_ROUTE,
            json={"title": TASK_TITLE},
            headers={"Operation-Id": str(uuid4())},
        )

    assert response.headers["Cache-Control"] == "no-store"

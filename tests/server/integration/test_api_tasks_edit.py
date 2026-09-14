"""End-to-end tests for editing a pending task over HTTP.

Covers PCE-11 through PCE-16, PCE-23, PCE-27, PCE-41, PCE-42, PCE-51,
PCE-52; REQ-007, REQ-008, REQ-010, REQ-029, REQ-031.

Every test composes the real application against a newly allocated
temporary database created by the explicit initializer, so no test
reaches any configured runtime database.

Editing answers protocol failures and durable rejections exactly as
creation does, so the suite checks that parity explicitly: a retained
rejection stays consultable, a protocol-only failure registers nothing.
"""

from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from task_analyzer_server import app as app_module
from task_analyzer_server import schema, services, storage
from task_analyzer_server.contracts import ErrorCode, FieldErrorCode
from task_analyzer_server.settings import ServerSettings

BUSY_TIMEOUT_MS = 5000

PRODUCT_ZONE = "America/Sao_Paulo"
SERVER_NOW = datetime(2026, 9, 14, 12, 0, 0, 123456, tzinfo=UTC)
CREATED_AT_TEXT = "2026-09-14T12:00:00.123456Z"

TASKS_ROUTE = "/v1/tasks"
OPERATIONS_ROUTE = "/v1/operations"

ORIGINAL_TITLE = "Read notes"
EDITED_TITLE = "Read the revised notes"
OTHER_TITLE = "Review the draft"
COMPLETED_TITLE = "Already finished"

ORIGINAL_OBSERVATIONS = "first note\nsecond note"
EDITED_OBSERVATIONS = "a different note"
DEADLINE = "2026-09-14"
OTHER_DEADLINE = "2026-09-20"

ABSENT_TASK_ID = UUID("30000000-0000-4000-8000-000000000009")

INSERT_COMPLETED_TASK = (
    "INSERT INTO tasks ("
    " task_id, title, title_key, observations, deadline_date,"
    " status, created_at_us, latest_completed_at_us, is_deleted"
    ") VALUES (?, ?, ?, NULL, NULL, 'completed', 0, 0, 0)"
)
READ_COMPLETED_TASK = (
    "SELECT title, status, latest_completed_at_us FROM tasks WHERE task_id = ?"
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


def create(client: TestClient, payload: object) -> dict[str, object]:
    """Create one task and return its stored snapshot.

    Args:
        client: The started test client.
        payload: The submitted task payload.

    Returns:
        The created task snapshot.

    Raises:
        AssertionError: If the creation was not accepted, which would
            make the test's premise untrue.
    """
    response = client.post(
        TASKS_ROUTE, json=payload, headers={"Operation-Id": str(uuid4())}
    )
    assert response.status_code == 201
    snapshot = response.json()["task"]
    assert isinstance(snapshot, dict)
    return snapshot


def edit(
    client: TestClient,
    task_id: object,
    payload: object,
    operation_id: UUID | None = None,
) -> tuple[UUID, dict[str, object]]:
    """Submit one edit attempt and return its identity and body.

    Args:
        client: The started test client.
        task_id: Identity of the task the request targets.
        payload: The submitted editable form state.
        operation_id: Identity to submit, generated when omitted.

    Returns:
        The submitted identity and the parsed response body.
    """
    identity = uuid4() if operation_id is None else operation_id
    response = client.put(
        f"{TASKS_ROUTE}/{task_id}",
        json=payload,
        headers={"Operation-Id": str(identity)},
    )
    return identity, {"status": response.status_code, **response.json()}


def stored_task(client: TestClient, task_id: object) -> dict[str, object]:
    """Read one managed task from the collection.

    Args:
        client: The started test client.
        task_id: Identity of the task to read.

    Returns:
        The stored snapshot of that task.

    Raises:
        AssertionError: If the task is not managed any more.
    """
    body = client.get(TASKS_ROUTE).json()
    found = [item for item in body["items"] if item["task_id"] == str(task_id)]
    assert len(found) == 1
    return dict(found[0])


def insert_completed_task(settings: ServerSettings, title: str) -> UUID:
    """Store one completed task, which 1A editing does not cover.

    Args:
        settings: Settings naming the disposable database.
        title: Title of the completed task.

    Returns:
        The identity of the completed task.
    """
    task_id = uuid4()
    with storage.open_connection(
        settings.database_path, BUSY_TIMEOUT_MS
    ) as connection:
        with storage.write_transaction(connection):
            connection.execute(
                INSERT_COMPLETED_TASK, (str(task_id), title, title)
            )
    return task_id


def completed_row(
    settings: ServerSettings, task_id: UUID
) -> tuple[object, ...]:
    """Read the stored columns of one completed task.

    Args:
        settings: Settings naming the disposable database.
        task_id: Identity of the completed task.

    Returns:
        Its title, status and completion timestamp.
    """
    with storage.open_connection(
        settings.database_path, BUSY_TIMEOUT_MS
    ) as connection:
        row = connection.execute(
            READ_COMPLETED_TASK, (str(task_id),)
        ).fetchone()
    return tuple(row)


def test_a_valid_edit_is_accepted_with_status_200(
    composed: FastAPI,
) -> None:
    """An accepted edit answers with the edited status."""
    with TestClient(composed) as client:
        created = create(client, {"title": ORIGINAL_TITLE})
        identity, body = edit(
            client, created["task_id"], {"title": EDITED_TITLE}
        )

    assert body["status"] == 200
    assert body["outcome"] == "succeeded"
    assert body["original_http_status"] == 200
    assert body["operation_id"] == str(identity)


def test_an_edit_publishes_the_updated_snapshot(
    composed: FastAPI,
) -> None:
    """The result carries the task exactly as it is now stored."""
    with TestClient(composed) as client:
        created = create(client, {"title": ORIGINAL_TITLE})
        _, body = edit(
            client,
            created["task_id"],
            {
                "title": EDITED_TITLE,
                "observations": EDITED_OBSERVATIONS,
                "deadline": OTHER_DEADLINE,
            },
        )
    task = body["task"]

    assert isinstance(task, dict)
    assert task["title"] == EDITED_TITLE
    assert task["observations"] == EDITED_OBSERVATIONS
    assert task["deadline"] == OTHER_DEADLINE


def test_an_edit_keeps_identity_creation_time_and_status(
    composed: FastAPI,
) -> None:
    """An edit never moves the server-owned fields."""
    with TestClient(composed) as client:
        created = create(client, {"title": ORIGINAL_TITLE})
        _, body = edit(client, created["task_id"], {"title": EDITED_TITLE})
    task = body["task"]

    assert isinstance(task, dict)
    assert task["task_id"] == created["task_id"]
    assert task["created_at"] == CREATED_AT_TEXT
    assert task["status"] == "pending"
    assert task["completed_at"] is None


def test_an_accepted_edit_is_persisted(composed: FastAPI) -> None:
    """The edited state is what the collection reports afterwards."""
    with TestClient(composed) as client:
        created = create(client, {"title": ORIGINAL_TITLE})
        edit(client, created["task_id"], {"title": EDITED_TITLE})

        assert stored_task(client, created["task_id"])["title"] == (
            EDITED_TITLE
        )


def test_omitting_an_optional_value_clears_it(composed: FastAPI) -> None:
    """A save carries the whole form, so an omission means absent."""
    with TestClient(composed) as client:
        created = create(
            client,
            {
                "title": ORIGINAL_TITLE,
                "observations": ORIGINAL_OBSERVATIONS,
                "deadline": DEADLINE,
            },
        )
        _, body = edit(client, created["task_id"], {"title": ORIGINAL_TITLE})
    task = body["task"]

    assert isinstance(task, dict)
    assert task["observations"] is None
    assert task["deadline"] is None


def test_an_explicit_null_clears_an_optional_value(
    composed: FastAPI,
) -> None:
    """An explicit null clears the value it is sent for."""
    with TestClient(composed) as client:
        created = create(
            client,
            {
                "title": ORIGINAL_TITLE,
                "observations": ORIGINAL_OBSERVATIONS,
                "deadline": DEADLINE,
            },
        )
        _, body = edit(
            client,
            created["task_id"],
            {
                "title": ORIGINAL_TITLE,
                "observations": None,
                "deadline": None,
            },
        )
        stored = stored_task(client, created["task_id"])
    task = body["task"]

    assert isinstance(task, dict)
    assert task["observations"] is None
    assert stored["deadline"] is None


def test_an_absent_target_is_a_retained_rejection(
    composed: FastAPI,
) -> None:
    """Editing a task that is not managed is rejected durably."""
    with TestClient(composed) as client:
        identity, body = edit(client, ABSENT_TASK_ID, {"title": EDITED_TITLE})
        consulted = client.get(f"{OPERATIONS_ROUTE}/{identity}")
    error = body["error"]

    assert body["status"] == 404
    assert body["outcome"] == "rejected"
    assert isinstance(error, dict)
    assert error["code"] == ErrorCode.TASK_NOT_FOUND.value
    assert consulted.status_code == 200
    assert consulted.json()["outcome"] == "rejected"


def test_an_absent_target_creates_no_task(composed: FastAPI) -> None:
    """No task is ever created through an edit."""
    with TestClient(composed) as client:
        edit(client, ABSENT_TASK_ID, {"title": EDITED_TITLE})
        body = client.get(TASKS_ROUTE).json()

    assert body["items"] == []


def test_a_completed_target_is_outside_this_command(
    composed: FastAPI, settings: ServerSettings
) -> None:
    """A target the 1A edit command does not cover is rejected."""
    target = insert_completed_task(settings, COMPLETED_TITLE)

    with TestClient(composed) as client:
        identity, body = edit(client, target, {"title": EDITED_TITLE})
        consulted = client.get(f"{OPERATIONS_ROUTE}/{identity}")
    error = body["error"]

    assert body["status"] == 409
    assert isinstance(error, dict)
    assert error["code"] == ErrorCode.TASK_STATE_INCOMPATIBLE.value
    assert consulted.json()["outcome"] == "rejected"


def test_a_completed_target_keeps_its_state_and_times(
    composed: FastAPI, settings: ServerSettings
) -> None:
    """The refused edit changes nothing about that task."""
    target = insert_completed_task(settings, COMPLETED_TITLE)
    before = completed_row(settings, target)

    with TestClient(composed) as client:
        edit(client, target, {"title": EDITED_TITLE})

    assert completed_row(settings, target) == before


def test_replaying_an_older_edit_returns_its_original_snapshot(
    composed: FastAPI,
) -> None:
    """A repeated older attempt answers with what it did then."""
    older = uuid4()

    with TestClient(composed) as client:
        created = create(client, {"title": ORIGINAL_TITLE})
        _, first = edit(
            client, created["task_id"], {"title": EDITED_TITLE}, older
        )
        edit(client, created["task_id"], {"title": OTHER_TITLE})
        _, replayed = edit(
            client, created["task_id"], {"title": EDITED_TITLE}, older
        )

    assert replayed == first


def test_replaying_an_older_edit_does_not_overwrite_current_state(
    composed: FastAPI,
) -> None:
    """The later accepted edit stays the task's current state."""
    older = uuid4()

    with TestClient(composed) as client:
        created = create(client, {"title": ORIGINAL_TITLE})
        edit(client, created["task_id"], {"title": EDITED_TITLE}, older)
        edit(client, created["task_id"], {"title": OTHER_TITLE})
        edit(client, created["task_id"], {"title": EDITED_TITLE}, older)

        assert stored_task(client, created["task_id"])["title"] == (
            OTHER_TITLE
        )


def test_an_invalid_edit_preserves_the_whole_task(
    composed: FastAPI,
) -> None:
    """A rejected edit leaves every stored field exactly as it was."""
    with TestClient(composed) as client:
        created = create(
            client,
            {
                "title": ORIGINAL_TITLE,
                "observations": ORIGINAL_OBSERVATIONS,
                "deadline": DEADLINE,
            },
        )
        _, body = edit(client, created["task_id"], {"title": ""})
        stored = stored_task(client, created["task_id"])
    error = body["error"]

    assert body["status"] == 422
    assert isinstance(error, dict)
    assert error["fields"] == [
        {"field": "title", "code": FieldErrorCode.TITLE_REQUIRED.value}
    ]
    assert stored == created


def test_an_invalid_field_type_is_a_retained_rejection(
    composed: FastAPI,
) -> None:
    """A type the contract refuses is decided inside the flow."""
    with TestClient(composed) as client:
        created = create(client, {"title": ORIGINAL_TITLE})
        identity, body = edit(
            client, created["task_id"], {"title": EDITED_TITLE, "deadline": 7}
        )
        consulted = client.get(f"{OPERATIONS_ROUTE}/{identity}")
    error = body["error"]

    assert body["status"] == 422
    assert isinstance(error, dict)
    assert error["fields"] == [
        {
            "field": "deadline",
            "code": FieldErrorCode.INVALID_FIELD_TYPE.value,
        }
    ]
    assert consulted.json()["error"]["fields"] == error["fields"]


def test_an_edit_into_a_taken_title_is_a_uniqueness_rejection(
    composed: FastAPI,
) -> None:
    """An edit obeys the same uniqueness rule creation does."""
    with TestClient(composed) as client:
        taken = create(client, {"title": OTHER_TITLE, "deadline": DEADLINE})
        edited = create(
            client, {"title": ORIGINAL_TITLE, "deadline": DEADLINE}
        )
        _, body = edit(
            client,
            edited["task_id"],
            {"title": OTHER_TITLE, "deadline": DEADLINE},
        )
        unchanged = stored_task(client, edited["task_id"])
    error = body["error"]

    assert body["status"] == 409
    assert isinstance(error, dict)
    assert error["code"] == ErrorCode.TASK_UNIQUENESS_CONFLICT.value
    assert error["conflicting_task_id"] == taken["task_id"]
    assert unchanged == edited


def test_reusing_an_identity_for_other_content_is_refused(
    composed: FastAPI,
) -> None:
    """A different edit under one identity is a protocol conflict."""
    identity = uuid4()

    with TestClient(composed) as client:
        created = create(client, {"title": ORIGINAL_TITLE})
        _, first = edit(
            client, created["task_id"], {"title": EDITED_TITLE}, identity
        )
        _, reused = edit(
            client, created["task_id"], {"title": OTHER_TITLE}, identity
        )
        consulted = client.get(f"{OPERATIONS_ROUTE}/{identity}").json()
        current = stored_task(client, created["task_id"])

    assert reused["status"] == 409
    assert isinstance(reused["error"], dict)
    assert reused["error"]["code"] == ErrorCode.OPERATION_ID_REUSED.value
    assert "outcome" not in reused
    assert consulted["task"] == first["task"]
    assert current["title"] == EDITED_TITLE


def test_an_unusable_operation_identity_registers_nothing(
    composed: FastAPI,
) -> None:
    """Editing answers an unusable identity exactly as creation does."""
    with TestClient(composed) as client:
        created = create(client, {"title": ORIGINAL_TITLE})
        response = client.put(
            f"{TASKS_ROUTE}/{created['task_id']}",
            json={"title": EDITED_TITLE},
            headers={"Operation-Id": "not-a-uuid"},
        )
        current = stored_task(client, created["task_id"])
    body = response.json()

    assert response.status_code == 400
    assert body["error"]["code"] == ErrorCode.INVALID_OPERATION_ENVELOPE.value
    assert "operation_id" not in body
    assert current == created


def test_an_unusable_task_target_registers_nothing(
    composed: FastAPI,
) -> None:
    """A target the server cannot read is an envelope failure."""
    identity = uuid4()

    with TestClient(composed) as client:
        response = client.put(
            f"{TASKS_ROUTE}/not-a-uuid",
            json={"title": EDITED_TITLE},
            headers={"Operation-Id": str(identity)},
        )
        consulted = client.get(f"{OPERATIONS_ROUTE}/{identity}")
    body = response.json()

    assert response.status_code == 400
    assert body["error"]["code"] == ErrorCode.INVALID_OPERATION_ENVELOPE.value
    assert body["operation_id"] == str(identity)
    assert consulted.status_code == 404


def test_an_unparseable_body_registers_nothing(composed: FastAPI) -> None:
    """Malformed JSON never enters the operation flow."""
    identity = uuid4()

    with TestClient(composed) as client:
        created = create(client, {"title": ORIGINAL_TITLE})
        response = client.put(
            f"{TASKS_ROUTE}/{created['task_id']}",
            content=b'{"title": ',
            headers={
                "Operation-Id": str(identity),
                "Content-Type": "application/json",
            },
        )
        consulted = client.get(f"{OPERATIONS_ROUTE}/{identity}")
        current = stored_task(client, created["task_id"])
    body = response.json()

    assert response.status_code == 400
    assert body["error"]["code"] == ErrorCode.INVALID_OPERATION_ENVELOPE.value
    assert consulted.status_code == 404
    assert current == created


def test_an_edit_before_zone_setup_is_refused(
    unconfigured: FastAPI,
) -> None:
    """A task command needs the product zone to be fixed first."""
    identity = uuid4()

    with TestClient(unconfigured) as client:
        _, body = edit(
            client, ABSENT_TASK_ID, {"title": EDITED_TITLE}, identity
        )
        consulted = client.get(f"{OPERATIONS_ROUTE}/{identity}")

    assert body["status"] == 409
    assert isinstance(body["error"], dict)
    assert body["error"]["code"] == ErrorCode.PRODUCT_TIME_ZONE_REQUIRED.value
    assert "outcome" not in body
    assert consulted.status_code == 404


def test_a_storage_failure_registers_no_outcome(
    composed: FastAPI, database_path: Path
) -> None:
    """An unavailable database confirms nothing and invents nothing."""
    with TestClient(composed) as client:
        created = create(client, {"title": ORIGINAL_TITLE})
        database_path.unlink()
        _, body = edit(client, created["task_id"], {"title": EDITED_TITLE})

    assert body["status"] == 503
    assert isinstance(body["error"], dict)
    assert body["error"]["code"] == ErrorCode.STORAGE_UNAVAILABLE.value
    assert "outcome" not in body
    assert "task" not in body


def test_an_edit_response_is_not_cacheable(composed: FastAPI) -> None:
    """An edit answer always comes from the server."""
    with TestClient(composed) as client:
        created = create(client, {"title": ORIGINAL_TITLE})
        response = client.put(
            f"{TASKS_ROUTE}/{created['task_id']}",
            json={"title": EDITED_TITLE},
            headers={"Operation-Id": str(uuid4())},
        )

    assert response.headers["Cache-Control"] == "no-store"

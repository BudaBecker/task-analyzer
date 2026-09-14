"""End-to-end tests for editing a pending task over HTTP.

Covers PCE-11 through PCE-16, PCE-23, PCE-27, PCE-41, PCE-42, PCE-51,
PCE-52; REQ-007, REQ-008, REQ-010, REQ-029, REQ-031.
"""

from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from helpers import FixedClock

from task_analyzer_server import app as app_module
from task_analyzer_server import services, storage
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


@pytest.fixture
def unconfigured(settings: ServerSettings) -> FastAPI:
    return app_module.create_app(settings, FixedClock(SERVER_NOW))


@pytest.fixture
def composed(settings: ServerSettings) -> FastAPI:
    services.configure_zone(settings, FixedClock(SERVER_NOW), PRODUCT_ZONE)
    return app_module.create_app(settings, FixedClock(SERVER_NOW))


def create(client: TestClient, payload: object) -> dict[str, object]:
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
    identity = uuid4() if operation_id is None else operation_id
    response = client.put(
        f"{TASKS_ROUTE}/{task_id}",
        json=payload,
        headers={"Operation-Id": str(identity)},
    )
    return identity, {"status": response.status_code, **response.json()}


def stored_task(client: TestClient, task_id: object) -> dict[str, object]:
    body = client.get(TASKS_ROUTE).json()
    found = [item for item in body["items"] if item["task_id"] == str(task_id)]
    assert len(found) == 1
    return dict(found[0])


def insert_completed_task(settings: ServerSettings, title: str) -> UUID:
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
    with TestClient(composed) as client:
        created = create(client, {"title": ORIGINAL_TITLE})
        edit(client, created["task_id"], {"title": EDITED_TITLE})

        assert stored_task(client, created["task_id"])["title"] == (
            EDITED_TITLE
        )


def test_omitting_an_optional_value_clears_it(composed: FastAPI) -> None:
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
    with TestClient(composed) as client:
        edit(client, ABSENT_TASK_ID, {"title": EDITED_TITLE})
        body = client.get(TASKS_ROUTE).json()

    assert body["items"] == []


def test_a_completed_target_is_outside_this_command(
    composed: FastAPI, settings: ServerSettings
) -> None:
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
    target = insert_completed_task(settings, COMPLETED_TITLE)
    before = completed_row(settings, target)

    with TestClient(composed) as client:
        edit(client, target, {"title": EDITED_TITLE})

    assert completed_row(settings, target) == before


def test_replaying_an_older_edit_returns_its_original_snapshot(
    composed: FastAPI,
) -> None:
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
    with TestClient(composed) as client:
        created = create(client, {"title": ORIGINAL_TITLE})
        response = client.put(
            f"{TASKS_ROUTE}/{created['task_id']}",
            json={"title": EDITED_TITLE},
            headers={"Operation-Id": str(uuid4())},
        )

    assert response.headers["Cache-Control"] == "no-store"

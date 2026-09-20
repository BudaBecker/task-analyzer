"""End-to-end tests for the lifecycle commands over HTTP.

Covers TLD-01 through TLD-32; REQ-008, REQ-009, REQ-010, REQ-025,
REQ-029, REQ-030, REQ-031.
"""

from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from helpers import FixedClock

from task_analyzer_server import app as app_module
from task_analyzer_server import services
from task_analyzer_server.contracts import ErrorCode, FieldErrorCode
from task_analyzer_server.settings import ServerSettings

PRODUCT_ZONE = "America/Sao_Paulo"
SERVER_NOW = datetime(2026, 9, 18, 11, 45, 0, 500000, tzinfo=UTC)
SERVER_NOW_TEXT = "2026-09-18T11:45:00.500000Z"

TASKS_ROUTE = "/v1/tasks"
OPERATIONS_ROUTE = "/v1/operations"

TITLE = "Read notes"
EQUIVALENT_TITLE = " READ  NOTES "
OTHER_TITLE = "Review the draft"
OBSERVATIONS = "first note\nsecond note"
DEADLINE = "2026-09-14"

ABSENT_TASK_ID = UUID("40000000-0000-4000-8000-000000000001")
UNUSABLE_TASK_ID = "not-a-task-identity"


@pytest.fixture
def composed(settings: ServerSettings) -> FastAPI:
    services.configure_zone(settings, FixedClock(SERVER_NOW), PRODUCT_ZONE)
    return app_module.create_app(settings, FixedClock(SERVER_NOW))


def create(
    client: TestClient,
    title: str = TITLE,
    observations: str | None = None,
    deadline: str | None = None,
) -> str:
    response = client.post(
        TASKS_ROUTE,
        json={
            "title": title,
            "observations": observations,
            "deadline": deadline,
        },
        headers={"Operation-Id": str(uuid4())},
    )
    assert response.status_code == 201
    return str(response.json()["task"]["task_id"])


def submit(
    client: TestClient,
    method: str,
    route: str,
    payload: object,
    operation_id: UUID | None = None,
) -> dict[str, object]:
    identity = uuid4() if operation_id is None else operation_id
    response = client.request(
        method,
        route,
        json=payload,
        headers={"Operation-Id": str(identity)},
    )
    return {"status": response.status_code, **response.json()}


def complete(
    client: TestClient,
    task_id: str,
    payload: object = None,
    operation_id: UUID | None = None,
) -> dict[str, object]:
    return submit(
        client,
        "POST",
        f"{TASKS_ROUTE}/{task_id}/completion",
        {} if payload is None else payload,
        operation_id,
    )


def edit_observations(
    client: TestClient,
    task_id: str,
    payload: object,
    operation_id: UUID | None = None,
) -> dict[str, object]:
    return submit(
        client,
        "PUT",
        f"{TASKS_ROUTE}/{task_id}/observations",
        payload,
        operation_id,
    )


def reopen(
    client: TestClient,
    task_id: str,
    payload: object = None,
    operation_id: UUID | None = None,
) -> dict[str, object]:
    return submit(
        client,
        "POST",
        f"{TASKS_ROUTE}/{task_id}/reopening",
        {} if payload is None else payload,
        operation_id,
    )


def delete(
    client: TestClient,
    task_id: str,
    payload: object = None,
    operation_id: UUID | None = None,
) -> dict[str, object]:
    return submit(
        client,
        "DELETE",
        f"{TASKS_ROUTE}/{task_id}",
        {} if payload is None else payload,
        operation_id,
    )


def completed(
    client: TestClient,
    title: str = TITLE,
    observations: str | None = None,
    deadline: str | None = None,
) -> str:
    task_id = create(client, title, observations, deadline)
    assert complete(client, task_id)["status"] == 200
    return task_id


def published_tasks(client: TestClient) -> list[dict[str, object]]:
    items = client.get(TASKS_ROUTE).json()["items"]
    assert isinstance(items, list)
    return [dict(item) for item in items]


def published_task(client: TestClient, task_id: str) -> dict[str, object]:
    found = [
        item for item in published_tasks(client) if item["task_id"] == task_id
    ]
    assert len(found) == 1
    return found[0]


def error_of(body: dict[str, object]) -> dict[str, object]:
    error = body["error"]
    assert isinstance(error, dict)
    return dict(error)


def snapshot_of(body: dict[str, object]) -> dict[str, object]:
    task = body["task"]
    assert isinstance(task, dict)
    return dict(task)


def test_completing_a_task_answers_200_with_the_completed_snapshot(
    composed: FastAPI,
) -> None:
    with TestClient(composed) as client:
        task_id = create(client, observations=OBSERVATIONS, deadline=DEADLINE)
        body = complete(client, task_id)

    assert body["status"] == 200
    assert body["outcome"] == "succeeded"
    snapshot = snapshot_of(body)
    assert snapshot["status"] == "completed"
    assert snapshot["completed_at"] == SERVER_NOW_TEXT
    assert snapshot["observations"] == OBSERVATIONS
    assert snapshot["deadline"] == DEADLINE


def test_a_published_task_keeps_its_completed_state(
    composed: FastAPI,
) -> None:
    with TestClient(composed) as client:
        task_id = completed(client)
        published = published_task(client, task_id)

    assert published["status"] == "completed"
    assert published["completed_at"] == SERVER_NOW_TEXT


def test_editing_completed_observations_answers_200(
    composed: FastAPI,
) -> None:
    with TestClient(composed) as client:
        task_id = completed(client)
        body = edit_observations(
            client, task_id, {"observations": OBSERVATIONS}
        )

    assert body["status"] == 200
    snapshot = snapshot_of(body)
    assert snapshot["observations"] == OBSERVATIONS
    assert snapshot["status"] == "completed"
    assert snapshot["completed_at"] == SERVER_NOW_TEXT


def test_reopening_answers_200_with_a_pending_snapshot(
    composed: FastAPI,
) -> None:
    with TestClient(composed) as client:
        task_id = completed(client, observations=OBSERVATIONS)
        body = reopen(client, task_id)

    assert body["status"] == 200
    snapshot = snapshot_of(body)
    assert snapshot["status"] == "pending"
    assert snapshot["completed_at"] is None
    assert snapshot["observations"] == OBSERVATIONS


def test_deleting_answers_200_with_the_final_snapshot(
    composed: FastAPI,
) -> None:
    with TestClient(composed) as client:
        task_id = completed(client, observations=OBSERVATIONS)
        body = delete(client, task_id)
        remaining = published_tasks(client)

    assert body["status"] == 200
    snapshot = snapshot_of(body)
    assert snapshot["task_id"] == task_id
    assert snapshot["status"] == "completed"
    assert snapshot["observations"] == OBSERVATIONS
    assert remaining == []


def test_a_deleted_task_frees_its_title_over_http(
    composed: FastAPI,
) -> None:
    with TestClient(composed) as client:
        task_id = create(client, deadline=DEADLINE)
        delete(client, task_id)
        response = client.post(
            TASKS_ROUTE,
            json={"title": EQUIVALENT_TITLE, "deadline": DEADLINE},
            headers={"Operation-Id": str(uuid4())},
        )

    assert response.status_code == 201


def test_a_second_completion_answers_409_state_incompatible(
    composed: FastAPI,
) -> None:
    with TestClient(composed) as client:
        task_id = completed(client)
        body = complete(client, task_id)
        published = published_task(client, task_id)

    assert body["status"] == 409
    assert body["outcome"] == "rejected"
    assert error_of(body)["code"] == ErrorCode.TASK_STATE_INCOMPATIBLE
    assert published["completed_at"] == SERVER_NOW_TEXT


def test_reopening_a_pending_task_answers_409_state_incompatible(
    composed: FastAPI,
) -> None:
    with TestClient(composed) as client:
        task_id = create(client)
        body = reopen(client, task_id)

    assert body["status"] == 409
    assert error_of(body)["code"] == ErrorCode.TASK_STATE_INCOMPATIBLE


def test_a_reopening_conflict_answers_409_and_names_the_task(
    composed: FastAPI,
) -> None:
    with TestClient(composed) as client:
        task_id = completed(client)
        conflicting = create(client, title=EQUIVALENT_TITLE)
        body = reopen(client, task_id)
        published = published_task(client, task_id)

    assert body["status"] == 409
    error = error_of(body)
    assert error["code"] == ErrorCode.TASK_UNIQUENESS_CONFLICT
    assert error["conflicting_task_id"] == conflicting
    assert published["status"] == "completed"


@pytest.mark.parametrize(
    ("method", "suffix"),
    [
        ("POST", "/completion"),
        ("POST", "/reopening"),
        ("DELETE", ""),
    ],
    ids=["complete", "reopen", "delete"],
)
def test_a_command_against_an_absent_task_answers_404(
    composed: FastAPI, method: str, suffix: str
) -> None:
    with TestClient(composed) as client:
        body = submit(
            client,
            method,
            f"{TASKS_ROUTE}/{ABSENT_TASK_ID}{suffix}",
            {},
        )
        remaining = published_tasks(client)

    assert body["status"] == 404
    assert error_of(body)["code"] == ErrorCode.TASK_NOT_FOUND
    assert remaining == []


def test_observations_against_an_absent_task_answers_404(
    composed: FastAPI,
) -> None:
    with TestClient(composed) as client:
        body = edit_observations(
            client,
            str(ABSENT_TASK_ID),
            {"observations": OBSERVATIONS},
        )

    assert body["status"] == 404
    assert error_of(body)["code"] == ErrorCode.TASK_NOT_FOUND


@pytest.mark.parametrize(
    ("payload", "expected_code"),
    [
        ({"title": OTHER_TITLE}, FieldErrorCode.UNEXPECTED_FIELD),
        ([], FieldErrorCode.INVALID_FIELD_TYPE),
        ("{}", FieldErrorCode.INVALID_FIELD_TYPE),
    ],
    ids=["extra_field", "array", "text"],
)
def test_a_completion_body_other_than_an_empty_object_is_rejected(
    composed: FastAPI, payload: object, expected_code: FieldErrorCode
) -> None:
    with TestClient(composed) as client:
        task_id = create(client)
        body = complete(client, task_id, payload)
        published = published_task(client, task_id)

    assert body["status"] == 422
    error = error_of(body)
    assert error["code"] == ErrorCode.TASK_VALIDATION_FAILED
    fields = error["fields"]
    assert isinstance(fields, list)
    assert fields[0]["code"] == expected_code
    assert published["status"] == "pending"


@pytest.mark.parametrize(
    ("payload", "expected_code"),
    [
        ({"observations": "a" * 5001}, FieldErrorCode.OBSERVATIONS_TOO_LONG),
        ({"observations": 5}, FieldErrorCode.INVALID_FIELD_TYPE),
        ({}, FieldErrorCode.INVALID_FIELD_TYPE),
        (
            {"observations": None, "title": OTHER_TITLE},
            FieldErrorCode.UNEXPECTED_FIELD,
        ),
    ],
    ids=["too_long", "wrong_type", "missing", "extra_field"],
)
def test_a_refused_observation_body_answers_422(
    composed: FastAPI, payload: object, expected_code: FieldErrorCode
) -> None:
    with TestClient(composed) as client:
        task_id = completed(client, observations=OBSERVATIONS)
        body = edit_observations(client, task_id, payload)
        published = published_task(client, task_id)

    assert body["status"] == 422
    error = error_of(body)
    assert error["code"] == ErrorCode.TASK_VALIDATION_FAILED
    fields = error["fields"]
    assert isinstance(fields, list)
    assert fields[0]["code"] == expected_code
    assert published["observations"] == OBSERVATIONS


def test_an_unusable_task_identity_is_a_protocol_error(
    composed: FastAPI,
) -> None:
    with TestClient(composed) as client:
        response = client.post(
            f"{TASKS_ROUTE}/{UNUSABLE_TASK_ID}/completion",
            json={},
            headers={"Operation-Id": str(uuid4())},
        )

    assert response.status_code == 400
    assert (
        response.json()["error"]["code"]
        == ErrorCode.INVALID_OPERATION_ENVELOPE
    )


def test_a_lifecycle_command_without_an_operation_id_is_refused(
    composed: FastAPI,
) -> None:
    with TestClient(composed) as client:
        task_id = create(client)
        response = client.post(f"{TASKS_ROUTE}/{task_id}/completion", json={})
        published = published_task(client, task_id)

    assert response.status_code == 400
    assert published["status"] == "pending"


@pytest.mark.parametrize(
    ("method", "suffix", "payload"),
    [
        ("POST", "/completion", {}),
        ("POST", "/reopening", {}),
        ("PUT", "/observations", {"observations": None}),
        ("DELETE", "", {}),
    ],
    ids=["complete", "reopen", "observations", "delete"],
)
def test_a_lifecycle_command_needs_the_product_time_zone(
    settings: ServerSettings, method: str, suffix: str, payload: object
) -> None:
    unconfigured = app_module.create_app(settings, FixedClock(SERVER_NOW))

    with TestClient(unconfigured) as client:
        response = client.request(
            method,
            f"{TASKS_ROUTE}/{ABSENT_TASK_ID}{suffix}",
            json=payload,
            headers={"Operation-Id": str(uuid4())},
        )

    assert response.status_code == 409
    assert (
        response.json()["error"]["code"]
        == ErrorCode.PRODUCT_TIME_ZONE_REQUIRED
    )


def test_a_completed_task_is_not_retitled_over_http(
    composed: FastAPI,
) -> None:
    with TestClient(composed) as client:
        task_id = completed(client)
        body = submit(
            client,
            "PUT",
            f"{TASKS_ROUTE}/{task_id}",
            {"title": OTHER_TITLE, "deadline": DEADLINE},
        )
        published = published_task(client, task_id)

    assert body["status"] == 409
    assert error_of(body)["code"] == ErrorCode.TASK_STATE_INCOMPATIBLE
    assert published["title"] == TITLE
    assert published["deadline"] is None
    assert published["status"] == "completed"


def test_a_repeated_lifecycle_request_answers_the_original_result(
    composed: FastAPI,
) -> None:
    identity = uuid4()
    with TestClient(composed) as client:
        task_id = create(client)
        original = complete(client, task_id, operation_id=identity)
        repeated = complete(client, task_id, operation_id=identity)

    assert repeated == original


def test_a_lost_lifecycle_response_is_recovered_by_consultation(
    composed: FastAPI,
) -> None:
    identity = uuid4()
    with TestClient(composed) as client:
        task_id = completed(client)
        original = delete(client, task_id, operation_id=identity)
        consulted = client.get(f"{OPERATIONS_ROUTE}/{identity}")

    assert consulted.status_code == 200
    assert consulted.json() == {
        key: value for key, value in original.items() if key != "status"
    }


def test_a_rejected_lifecycle_result_is_also_recoverable(
    composed: FastAPI,
) -> None:
    identity = uuid4()
    with TestClient(composed) as client:
        task_id = create(client)
        rejected = reopen(client, task_id, operation_id=identity)
        consulted = client.get(f"{OPERATIONS_ROUTE}/{identity}")

    assert rejected["status"] == 409
    assert consulted.status_code == 200
    assert (
        consulted.json()["error"]["code"] == ErrorCode.TASK_STATE_INCOMPATIBLE
    )


def test_one_identity_reused_for_another_command_answers_409(
    composed: FastAPI,
) -> None:
    identity = uuid4()
    with TestClient(composed) as client:
        task_id = create(client)
        original = complete(client, task_id, operation_id=identity)
        reused = reopen(client, task_id, operation_id=identity)
        consulted = client.get(f"{OPERATIONS_ROUTE}/{identity}")

    assert reused["status"] == 409
    assert reused["error"]["code"] == ErrorCode.OPERATION_ID_REUSED  # type: ignore[index]
    assert consulted.json() == {
        key: value for key, value in original.items() if key != "status"
    }


def test_the_whole_lifecycle_is_reachable_over_http(
    composed: FastAPI,
) -> None:
    with TestClient(composed) as client:
        task_id = create(client)
        complete(client, task_id)
        edit_observations(client, task_id, {"observations": OBSERVATIONS})
        reopen(client, task_id)
        reopened = published_task(client, task_id)
        recompleted = complete(client, task_id)
        delete(client, task_id)
        remaining = published_tasks(client)

    assert reopened["status"] == "pending"
    assert reopened["observations"] == OBSERVATIONS
    assert snapshot_of(recompleted)["completed_at"] == SERVER_NOW_TEXT
    assert remaining == []

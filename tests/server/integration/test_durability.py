"""Integration tests for durability across restarts and sessions.

Covers PCE-34, PCE-35, PCE-36 and the lifecycle persistence TLD-28,
TLD-29 and TLD-31; REQ-010, REQ-028, REQ-031.
"""

import os
import socket
import subprocess
import sys
import time
from collections.abc import Iterator
from contextlib import closing, contextmanager
from datetime import date, datetime
from pathlib import Path
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

import httpx
import pytest

from task_analyzer_server import schema
from task_analyzer_server.settings import (
    DATABASE_PATH_VARIABLE,
    LOG_LEVEL_VARIABLE,
)

RUNTIME_ENTRY = "task_analyzer_server.app:application_factory"
HOST = "127.0.0.1"

READINESS_TIMEOUT_SECONDS = 60.0
POLL_INTERVAL_SECONDS = 0.05
REQUEST_TIMEOUT_SECONDS = 10.0
STOP_TIMEOUT_SECONDS = 30.0

CONFIGURATION_ROUTE = "/v1/configuration"
TASKS_ROUTE = "/v1/tasks"
OPERATIONS_ROUTE = "/v1/operations"

PRODUCT_ZONE = "America/Sao_Paulo"
FAR_EAST_ZONE = "Pacific/Kiritimati"
FAR_WEST_ZONE = "Pacific/Niue"

ORIGINAL_TITLE = "Read notes"
EDITED_TITLE = "Read the revised notes"
LATER_TITLE = "Review the draft"
OBSERVATIONS = "first note\nsecond note"
DEADLINE = "2026-09-14"


def free_port() -> int:
    with closing(socket.socket()) as probe:
        probe.bind((HOST, 0))
        return int(probe.getsockname()[1])


def initialized_database(directory: Path) -> Path:
    target = directory / "disposable.sqlite3"
    schema.initialize_database(target)
    return target


def server_environment(database: Path) -> dict[str, str]:
    environment = {
        name: value
        for name, value in os.environ.items()
        if name not in {DATABASE_PATH_VARIABLE, LOG_LEVEL_VARIABLE}
    }
    environment[DATABASE_PATH_VARIABLE] = str(database)
    environment[LOG_LEVEL_VARIABLE] = "INFO"
    return environment


@contextmanager
def running_server(database: Path, workspace: Path) -> Iterator[str]:
    port = free_port()
    log = workspace / f"server-{port}.log"
    with log.open("wb") as sink:
        process = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "uvicorn",
                RUNTIME_ENTRY,
                "--factory",
                "--host",
                HOST,
                "--port",
                str(port),
            ],
            cwd=str(workspace),
            env=server_environment(database),
            stdout=sink,
            stderr=subprocess.STDOUT,
        )
        try:
            base_url = f"http://{HOST}:{port}"
            _await_readiness(process, base_url, log)
            yield base_url
        finally:
            stop(process)


def stop(process: "subprocess.Popen[bytes]") -> None:
    if process.poll() is None:
        process.terminate()
    try:
        process.wait(timeout=STOP_TIMEOUT_SECONDS)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=STOP_TIMEOUT_SECONDS)


def _await_readiness(
    process: "subprocess.Popen[bytes]", base_url: str, log: Path
) -> None:
    deadline = time.monotonic() + READINESS_TIMEOUT_SECONDS
    with httpx.Client(timeout=REQUEST_TIMEOUT_SECONDS) as client:
        while time.monotonic() < deadline:
            if process.poll() is not None:
                raise AssertionError(
                    f"The server exited with {process.returncode} before"
                    f" it was ready:"
                    f" {log.read_text(encoding='utf-8', errors='replace')}"
                )
            try:
                client.get(f"{base_url}{CONFIGURATION_ROUTE}")
            except httpx.HTTPError:
                time.sleep(POLL_INTERVAL_SECONDS)
            else:
                return
    raise AssertionError(
        "The server was not ready within"
        f" {READINESS_TIMEOUT_SECONDS} seconds:"
        f" {log.read_text(encoding='utf-8', errors='replace')}"
    )


def configure(base_url: str, zone_key: str = PRODUCT_ZONE) -> None:
    with httpx.Client(timeout=REQUEST_TIMEOUT_SECONDS) as client:
        response = client.put(
            f"{base_url}{CONFIGURATION_ROUTE}",
            json={"product_time_zone": zone_key},
        )
    assert response.status_code == 200


def create(
    base_url: str, payload: object, operation_id: UUID | None = None
) -> httpx.Response:
    identity = uuid4() if operation_id is None else operation_id
    with httpx.Client(timeout=REQUEST_TIMEOUT_SECONDS) as client:
        return client.post(
            f"{base_url}{TASKS_ROUTE}",
            json=payload,
            headers={"Operation-Id": str(identity)},
        )


def edit(base_url: str, task_id: str, payload: object) -> httpx.Response:
    with httpx.Client(timeout=REQUEST_TIMEOUT_SECONDS) as client:
        return client.put(
            f"{base_url}{TASKS_ROUTE}/{task_id}",
            json=payload,
            headers={"Operation-Id": str(uuid4())},
        )


def lifecycle(
    base_url: str,
    method: str,
    route: str,
    operation_id: UUID | None = None,
) -> httpx.Response:
    identity = uuid4() if operation_id is None else operation_id
    with httpx.Client(timeout=REQUEST_TIMEOUT_SECONDS) as client:
        return client.request(
            method,
            f"{base_url}{route}",
            json={},
            headers={"Operation-Id": str(identity)},
        )


def read(base_url: str, route: str) -> httpx.Response:
    with httpx.Client(timeout=REQUEST_TIMEOUT_SECONDS) as client:
        return client.get(f"{base_url}{route}")


def only_task(base_url: str) -> dict[str, object]:
    items = read(base_url, TASKS_ROUTE).json()["items"]
    assert len(items) == 1
    return dict(items[0])


def product_date_of(body: dict[str, object]) -> date:
    return date.fromisoformat(str(body["product_date"]))


def expected_product_date(body: dict[str, object], zone_key: str) -> date:
    sampled = datetime.fromisoformat(
        str(body["server_now"]).replace("Z", "+00:00")
    )
    return sampled.astimezone(ZoneInfo(zone_key)).date()


@pytest.fixture
def database(tmp_path: Path) -> Path:
    return initialized_database(tmp_path)


def test_a_created_task_survives_a_new_server_process(
    database: Path, tmp_path: Path
) -> None:
    with running_server(database, tmp_path) as first:
        configure(first)
        created = create(first, {"title": ORIGINAL_TITLE})
    with running_server(database, tmp_path) as second:
        survivor = only_task(second)

    assert created.status_code == 201
    assert survivor["title"] == ORIGINAL_TITLE


def test_a_created_task_is_unchanged_by_the_restart(
    database: Path, tmp_path: Path
) -> None:
    with running_server(database, tmp_path) as first:
        configure(first)
        created = create(
            first,
            {
                "title": ORIGINAL_TITLE,
                "observations": OBSERVATIONS,
                "deadline": DEADLINE,
            },
        )
    with running_server(database, tmp_path) as second:
        survivor = only_task(second)

    assert survivor == created.json()["task"]


def test_an_edited_task_survives_a_new_server_process(
    database: Path, tmp_path: Path
) -> None:
    with running_server(database, tmp_path) as first:
        configure(first)
        created = create(first, {"title": ORIGINAL_TITLE})
        task_id = str(created.json()["task"]["task_id"])
        edited = edit(
            first,
            task_id,
            {"title": EDITED_TITLE, "observations": OBSERVATIONS},
        )
    with running_server(database, tmp_path) as second:
        survivor = only_task(second)

    assert edited.status_code == 200
    assert survivor == edited.json()["task"]


def test_an_edit_keeps_identity_and_creation_time_across_a_restart(
    database: Path, tmp_path: Path
) -> None:
    with running_server(database, tmp_path) as first:
        configure(first)
        created = create(first, {"title": ORIGINAL_TITLE}).json()["task"]
        edit(first, str(created["task_id"]), {"title": EDITED_TITLE})
    with running_server(database, tmp_path) as second:
        survivor = only_task(second)

    assert survivor["task_id"] == created["task_id"]
    assert survivor["created_at"] == created["created_at"]
    assert survivor["status"] == "pending"


def test_the_configured_product_zone_survives_a_restart(
    database: Path, tmp_path: Path
) -> None:
    with running_server(database, tmp_path) as first:
        configure(first)
    with running_server(database, tmp_path) as second:
        configuration = read(second, CONFIGURATION_ROUTE).json()

    assert configuration["configured"] is True
    assert configuration["product_time_zone"] == PRODUCT_ZONE


def test_deadline_interpretation_still_uses_the_retained_zone(
    tmp_path: Path,
) -> None:
    east_home = tmp_path / "east"
    west_home = tmp_path / "west"
    east_home.mkdir()
    west_home.mkdir()
    east = initialized_database(east_home)
    west = initialized_database(west_home)

    with running_server(east, east_home) as server:
        configure(server, FAR_EAST_ZONE)
    with running_server(west, west_home) as server:
        configure(server, FAR_WEST_ZONE)
    with running_server(east, east_home) as server:
        east_reading = read(server, TASKS_ROUTE).json()
    with running_server(west, west_home) as server:
        west_reading = read(server, TASKS_ROUTE).json()

    assert product_date_of(east_reading) == expected_product_date(
        east_reading, FAR_EAST_ZONE
    )
    assert product_date_of(west_reading) == expected_product_date(
        west_reading, FAR_WEST_ZONE
    )
    assert product_date_of(east_reading) != product_date_of(west_reading)


def test_a_fresh_client_session_reads_the_persisted_state(
    database: Path, tmp_path: Path
) -> None:
    with running_server(database, tmp_path) as first:
        configure(first)
        created = create(first, {"title": ORIGINAL_TITLE})
    with running_server(database, tmp_path) as second:
        reading = read(second, TASKS_ROUTE)

    assert "set-cookie" not in reading.headers
    assert reading.json()["product_time_zone"] == PRODUCT_ZONE
    assert [item["task_id"] for item in reading.json()["items"]] == [
        created.json()["task"]["task_id"]
    ]


def test_the_original_operation_outcome_is_consultable_after_a_restart(
    database: Path, tmp_path: Path
) -> None:
    identity = uuid4()

    with running_server(database, tmp_path) as first:
        configure(first)
        original = create(first, {"title": ORIGINAL_TITLE}, identity)
    with running_server(database, tmp_path) as second:
        consulted = read(second, f"{OPERATIONS_ROUTE}/{identity}")

    assert consulted.status_code == 200
    assert consulted.json() == original.json()


def test_the_restarted_server_accepts_new_work_on_persisted_state(
    database: Path, tmp_path: Path
) -> None:
    with running_server(database, tmp_path) as first:
        configure(first)
        create(first, {"title": ORIGINAL_TITLE})
    with running_server(database, tmp_path) as second:
        added = create(second, {"title": LATER_TITLE})
        titles = {
            item["title"] for item in read(second, TASKS_ROUTE).json()["items"]
        }

    assert added.status_code == 201
    assert titles == {ORIGINAL_TITLE, LATER_TITLE}


def test_a_disposable_server_never_falls_back_to_a_runtime_database(
    database: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(DATABASE_PATH_VARIABLE, "C:/runtime/production.db")

    environment = server_environment(database)
    with running_server(database, tmp_path) as server:
        configure(server)
        created = create(server, {"title": ORIGINAL_TITLE})

    assert environment[DATABASE_PATH_VARIABLE] == str(database)
    assert created.status_code == 201
    assert database.stat().st_size > 0
    assert not Path("C:/runtime/production.db").exists()


def test_a_completed_task_survives_a_new_server_process(
    database: Path, tmp_path: Path
) -> None:
    with running_server(database, tmp_path) as first:
        configure(first)
        created = create(first, {"title": ORIGINAL_TITLE})
        task_id = str(created.json()["task"]["task_id"])
        completed = lifecycle(
            first, "POST", f"{TASKS_ROUTE}/{task_id}/completion"
        )
    with running_server(database, tmp_path) as second:
        survivor = only_task(second)

    assert completed.status_code == 200
    assert survivor == completed.json()["task"]
    assert survivor["status"] == "completed"


def test_a_reopened_task_survives_a_new_server_process(
    database: Path, tmp_path: Path
) -> None:
    with running_server(database, tmp_path) as first:
        configure(first)
        created = create(first, {"title": ORIGINAL_TITLE})
        task_id = str(created.json()["task"]["task_id"])
        lifecycle(first, "POST", f"{TASKS_ROUTE}/{task_id}/completion")
        reopened = lifecycle(
            first, "POST", f"{TASKS_ROUTE}/{task_id}/reopening"
        )
    with running_server(database, tmp_path) as second:
        survivor = only_task(second)

    assert reopened.status_code == 200
    assert survivor["status"] == "pending"
    assert survivor["completed_at"] is None
    assert survivor["created_at"] == created.json()["task"]["created_at"]


def test_edited_completed_observations_survive_a_restart(
    database: Path, tmp_path: Path
) -> None:
    with running_server(database, tmp_path) as first:
        configure(first)
        created = create(first, {"title": ORIGINAL_TITLE})
        task_id = str(created.json()["task"]["task_id"])
        completed = lifecycle(
            first, "POST", f"{TASKS_ROUTE}/{task_id}/completion"
        )
        with httpx.Client(timeout=REQUEST_TIMEOUT_SECONDS) as client:
            edited = client.put(
                f"{first}{TASKS_ROUTE}/{task_id}/observations",
                json={"observations": OBSERVATIONS},
                headers={"Operation-Id": str(uuid4())},
            )
    with running_server(database, tmp_path) as second:
        survivor = only_task(second)

    assert edited.status_code == 200
    assert survivor == edited.json()["task"]
    assert survivor["observations"] == OBSERVATIONS
    assert survivor["status"] == "completed"
    assert survivor["completed_at"] == completed.json()["task"]["completed_at"]


def test_a_deleted_task_stays_absent_after_a_restart(
    database: Path, tmp_path: Path
) -> None:
    identity = uuid4()

    with running_server(database, tmp_path) as first:
        configure(first)
        created = create(first, {"title": ORIGINAL_TITLE})
        task_id = str(created.json()["task"]["task_id"])
        deleted = lifecycle(
            first, "DELETE", f"{TASKS_ROUTE}/{task_id}", identity
        )
    with running_server(database, tmp_path) as second:
        remaining = read(second, TASKS_ROUTE).json()["items"]
        consulted = read(second, f"{OPERATIONS_ROUTE}/{identity}")

    assert deleted.status_code == 200
    assert remaining == []
    assert consulted.json() == deleted.json()
    assert consulted.json()["task"]["task_id"] == task_id


def test_a_lost_lifecycle_response_is_still_recoverable_afterwards(
    database: Path, tmp_path: Path
) -> None:
    identity = uuid4()

    with running_server(database, tmp_path) as first:
        configure(first)
        created = create(first, {"title": ORIGINAL_TITLE})
        task_id = str(created.json()["task"]["task_id"])
        original = lifecycle(
            first, "POST", f"{TASKS_ROUTE}/{task_id}/completion", identity
        )
    with running_server(database, tmp_path) as second:
        consulted = read(second, f"{OPERATIONS_ROUTE}/{identity}")
        repeated = lifecycle(
            second, "POST", f"{TASKS_ROUTE}/{task_id}/completion", identity
        )
        survivor = only_task(second)

    assert consulted.json() == original.json()
    assert repeated.json() == original.json()
    assert survivor["completed_at"] == original.json()["task"]["completed_at"]

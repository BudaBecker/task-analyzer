"""F1-F5 regressions: REQ-007/010/028/031, PCE-15/30/34/38/43.
"""

import json
import logging
import sqlite3
import threading
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing, contextmanager
from pathlib import Path
from uuid import uuid4

import pytest
import uvicorn
from fastapi.testclient import TestClient

from task_analyzer_server import app, schema, services, storage
from task_analyzer_server.clock import SystemClock
from task_analyzer_server.contracts import OperationRequest
from task_analyzer_server.logging_config import configure_logging
from task_analyzer_server.settings import ServerSettings


@pytest.fixture
def settings(tmp_path: Path) -> ServerSettings:
    path = tmp_path / "disposable.sqlite3"
    schema.initialize_database(path)
    return ServerSettings(path, "INFO", 2000)


def test_concurrent_initializer_preserves_the_winners_data(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "disposable.sqlite3"
    both_entered = threading.Barrier(2)
    winner_done = threading.Event()
    read_schema = schema.read_initial_schema
    outcomes: dict[str, Exception | None] = {}

    def scheduled_schema() -> str:
        script = read_schema()
        both_entered.wait(timeout=5)
        if threading.current_thread().name == "loser":
            assert winner_done.wait(timeout=5)
        return script

    def initialize() -> None:
        name = threading.current_thread().name
        try:
            schema.initialize_database(target)
            with closing(sqlite3.connect(target)) as connection:
                connection.execute(
                    "INSERT INTO product_configuration VALUES (1, 'UTC')"
                )
                connection.commit()
            outcomes[name] = None
        except Exception as error:
            outcomes[name] = error
        finally:
            if name == "winner":
                winner_done.set()

    monkeypatch.setattr(schema, "read_initial_schema", scheduled_schema)
    threads = [
        threading.Thread(target=initialize, name=name)
        for name in ("winner", "loser")
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)
        assert not thread.is_alive()
    assert outcomes["winner"] is None
    assert isinstance(outcomes["loser"], schema.DatabaseAlreadyExistsError)
    with closing(sqlite3.connect(target)) as connection:
        assert connection.execute(
            "SELECT product_time_zone FROM product_configuration"
        ).fetchone() == ("UTC",)


@pytest.mark.parametrize(
    "method,route,payload",
    [
        ("POST", "/v1/tasks", {"title": "blocked"}),
        (
            "PUT",
            "/v1/tasks/20000000-0000-4000-8000-000000000001",
            {"title": "blocked"},
        ),
        ("PUT", "/v1/configuration", {"product_time_zone": "UTC"}),
    ],
)
def test_reads_progress_while_an_http_write_waits_for_sqlite(
    settings: ServerSettings,
    monkeypatch: pytest.MonkeyPatch,
    method: str,
    route: str,
    payload: dict[str, str],
) -> None:
    clock = SystemClock()
    services.configure_zone(settings, clock, "UTC")
    entered = threading.Event()
    original = storage.write_transaction

    @contextmanager
    def observed_write(connection: sqlite3.Connection) -> Iterator[None]:
        entered.set()
        with original(connection):
            yield

    monkeypatch.setattr(storage, "write_transaction", observed_write)
    with TestClient(app.create_app(settings, clock)) as client:
        with closing(sqlite3.connect(settings.database_path)) as holder:
            holder.execute("BEGIN IMMEDIATE")
            with ThreadPoolExecutor(max_workers=1) as executor:
                pending = executor.submit(
                    client.request,
                    method,
                    route,
                    json=payload,
                    headers={"Operation-Id": str(uuid4())},
                )
                assert entered.wait(timeout=5)
                read = client.get("/v1/configuration")
                assert read.status_code == 200
                assert not pending.done(), (
                    "the read waited for the blocked write"
                )
                result = pending.result(timeout=5)
                assert result.status_code == 503
                assert result.json()["error"]["code"] == "STORAGE_UNAVAILABLE"
            holder.rollback()


@pytest.mark.parametrize(
    "method,route",
    [
        ("POST", "/v1/tasks"),
        ("PUT", "/v1/tasks/20000000-0000-4000-8000-000000000001"),
    ],
)
@pytest.mark.parametrize("number", ["NaN", "Infinity", "-Infinity", "1e309"])
def test_json_numbers_follow_the_protocol_and_durable_validation_contract(
    settings: ServerSettings,
    method: str,
    route: str,
    number: str,
) -> None:
    clock = SystemClock()
    services.configure_zone(settings, clock, "UTC")
    identity = uuid4()
    with TestClient(app.create_app(settings, clock)) as client:
        response = client.request(
            method,
            route,
            content='{"title":' + number + "}",
            headers={
                "Operation-Id": str(identity),
                "Content-Type": "application/json",
            },
        )
        consulted = client.get(f"/v1/operations/{identity}")
        if number == "1e309":
            assert response.status_code == 422
            assert response.json()["outcome"] == "rejected"
            assert response.json()["error"]["fields"] == [
                {"field": "title", "code": "INVALID_FIELD_TYPE"}
            ]
            assert consulted.status_code == 200
            assert consulted.json() == response.json()
            replay = client.request(
                method,
                route,
                content='{"title":' + number + "}",
                headers={"Operation-Id": str(identity)},
            )
            assert replay.json() == response.json()
        else:
            assert response.status_code == 400
            assert (
                response.json()["error"]["code"]
                == "INVALID_OPERATION_ENVELOPE"
            )
            assert consulted.status_code == 404
        assert client.get("/v1/tasks").json()["items"] == []


def test_task_list_uses_one_snapshot_during_zone_setup(
    settings: ServerSettings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clock = SystemClock()
    original = storage.read_product_time_zone
    first_read = True
    competing = ServerSettings(settings.database_path, "INFO", 1)

    def configure_after_read(connection: sqlite3.Connection) -> str | None:
        nonlocal first_read
        zone = original(connection)
        if first_read:
            first_read = False
            # Separate SQLite connections attempt a commit during this read.
            # A coherent read snapshot keeps setup from committing until close.
            try:
                services.configure_zone(competing, clock, "UTC")
                services.create_task(
                    competing,
                    clock,
                    OperationRequest(
                        uuid4(), "POST", "/v1/tasks", {"title": "after setup"}
                    ),
                )
            except sqlite3.OperationalError as error:
                assert "locked" in str(error)
        return zone

    monkeypatch.setattr(
        storage, "read_product_time_zone", configure_after_read
    )
    reading = services.read_task_list(settings, clock)
    assert reading.product_time_zone is None
    assert reading.product_date is None
    assert reading.items == ()
    services.configure_zone(settings, clock, "UTC")
    assert services.read_task_list(settings, clock).product_time_zone == "UTC"


def test_actual_uvicorn_configuration_emits_json_without_duplicate_records(
    capsys: pytest.CaptureFixture[str],
) -> None:
    names = ("", "uvicorn", "uvicorn.error", "uvicorn.access")
    saved = [
        (
            logging.getLogger(name),
            list(logging.getLogger(name).handlers),
            logging.getLogger(name).level,
            logging.getLogger(name).propagate,
        )
        for name in names
    ]
    try:
        uvicorn.Config(
            "task_analyzer_server.app:application_factory", factory=True
        )
        configure_logging("INFO")
        for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
            logging.getLogger(name).info("runtime_probe")
        lines = capsys.readouterr().err.splitlines()
        assert len(lines) == 3
        for line in lines:
            record = json.loads(line)
            assert record["event"] == "runtime_probe"
            assert record["level"] == "INFO"
            assert "request_id" in record
    finally:
        for logger, handlers, level, propagate in saved:
            logger.handlers = handlers
            logger.setLevel(level)
            logger.propagate = propagate

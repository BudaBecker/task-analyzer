"""End-to-end tests for composition, startup and shared handlers.

Covers PCE-34, PCE-35, PCE-44, PCE-45, PCE-46, PCE-47; REQ-003, REQ-010,
REQ-027, REQ-028.
"""

import logging
import platform
import sqlite3
import subprocess
import sys
from collections.abc import Iterator
from contextlib import closing
from datetime import UTC, datetime
from inspect import signature
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI, Request, Response
from fastapi.testclient import TestClient
from helpers import FixedClock

from task_analyzer_server import api, services
from task_analyzer_server import app as app_module
from task_analyzer_server.contracts import ErrorCode, OperationRequest
from task_analyzer_server.settings import (
    DATABASE_PATH_VARIABLE,
    LOG_LEVEL_VARIABLE,
    ServerSettings,
)

BUSY_TIMEOUT_MS = 5000

PRODUCT_ZONE = "America/Sao_Paulo"
SERVER_NOW = datetime(2026, 9, 14, 12, 0, 0, 123456, tzinfo=UTC)

TASK_TITLE = "Read notes"
TASK_TARGET = "/v1/tasks"

UNKNOWN_OPERATION_ID = UUID("10000000-0000-4000-8000-000000000009")

PROTOCOL_ERROR_FIELDS = frozenset({"request_id", "error"})
PROTOCOL_ERROR_FIELDS_WITH_OPERATION = frozenset(
    {"request_id", "error", "operation_id"}
)

FORWARDED_IDENTITY_HEADERS = {
    "Authorization": "Bearer not-a-product-account",
    "X-Forwarded-User": "someone@example.com",
    "Tailscale-User-Login": "someone@example.com",
}

SET_SCHEMA_VERSION = "UPDATE schema_version SET version = 2"


@pytest.fixture
def composed(settings: ServerSettings) -> FastAPI:
    return app_module.create_app(settings, FixedClock(SERVER_NOW))


@pytest.fixture
def restored_root_logging() -> Iterator[None]:
    root = logging.getLogger()
    handlers = list(root.handlers)
    level = root.level
    try:
        yield
    finally:
        for installed in list(root.handlers):
            root.removeHandler(installed)
        for original in handlers:
            root.addHandler(original)
        root.setLevel(level)


def settings_for(path: Path) -> ServerSettings:
    return ServerSettings(
        database_path=path,
        log_level="INFO",
        db_busy_timeout_ms=BUSY_TIMEOUT_MS,
    )


def stored_creation(settings: ServerSettings) -> UUID:
    clock = FixedClock(SERVER_NOW)
    services.configure_zone(settings, clock, PRODUCT_ZONE)
    operation_id = uuid4()
    services.create_task(
        settings,
        clock,
        OperationRequest(
            operation_id=operation_id,
            method="POST",
            target=TASK_TARGET,
            payload={"title": TASK_TITLE},
        ),
    )
    return operation_id


def test_startup_serves_requests_against_an_initialized_database(
    composed: FastAPI, settings: ServerSettings
) -> None:
    operation_id = stored_creation(settings)

    with TestClient(composed) as client:
        response = client.get(f"/v1/operations/{operation_id}")

    assert response.status_code == 200


def test_startup_succeeds_when_no_product_zone_is_configured(
    composed: FastAPI,
) -> None:
    with TestClient(composed) as client:
        response = client.get(f"/v1/operations/{UNKNOWN_OPERATION_ID}")

    assert response.status_code == 404


def test_startup_fails_visibly_when_the_database_is_absent(
    tmp_path: Path,
) -> None:
    missing = tmp_path / "absent.sqlite3"
    composed = app_module.create_app(
        settings_for(missing), FixedClock(SERVER_NOW)
    )

    with pytest.raises(app_module.StartupVerificationError) as failure:
        with TestClient(composed):
            pass

    assert str(missing) in str(failure.value)


def test_startup_does_not_create_an_absent_database(tmp_path: Path) -> None:
    missing = tmp_path / "absent.sqlite3"
    composed = app_module.create_app(
        settings_for(missing), FixedClock(SERVER_NOW)
    )

    with pytest.raises(app_module.StartupVerificationError):
        with TestClient(composed):
            pass

    assert not missing.exists()


def test_startup_fails_visibly_on_an_incompatible_schema_version(
    database_path: Path,
) -> None:
    with closing(sqlite3.connect(database_path)) as connection:
        connection.execute(SET_SCHEMA_VERSION)
        connection.commit()
    composed = app_module.create_app(
        settings_for(database_path), FixedClock(SERVER_NOW)
    )

    with pytest.raises(app_module.StartupVerificationError) as failure:
        with TestClient(composed):
            pass

    assert "schema version 2" in str(failure.value)


def test_startup_fails_visibly_when_the_schema_is_absent(
    tmp_path: Path,
) -> None:
    foreign = tmp_path / "foreign.sqlite3"
    with closing(sqlite3.connect(foreign)) as connection:
        connection.execute("CREATE TABLE something (value TEXT)")
        connection.commit()
    composed = app_module.create_app(
        settings_for(foreign), FixedClock(SERVER_NOW)
    )

    with pytest.raises(app_module.StartupVerificationError) as failure:
        with TestClient(composed):
            pass

    assert str(foreign) in str(failure.value)


def test_the_runtime_factory_takes_no_arguments() -> None:
    assert signature(app_module.application_factory).parameters == {}


def test_the_runtime_factory_composes_from_the_environment(
    database_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    restored_root_logging: None,
) -> None:
    monkeypatch.setenv(DATABASE_PATH_VARIABLE, str(database_path))
    monkeypatch.setenv(LOG_LEVEL_VARIABLE, "DEBUG")

    built = app_module.application_factory()

    assert built.state.settings == ServerSettings(
        database_path=database_path,
        log_level="DEBUG",
        db_busy_timeout_ms=BUSY_TIMEOUT_MS,
    )


def test_the_runtime_factory_creates_no_database(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    restored_root_logging: None,
) -> None:
    missing = tmp_path / "absent.sqlite3"
    monkeypatch.setenv(DATABASE_PATH_VARIABLE, str(missing))

    app_module.application_factory()

    assert not missing.exists()


def test_composing_the_application_creates_no_database(tmp_path: Path) -> None:
    missing = tmp_path / "absent.sqlite3"

    app_module.create_app(settings_for(missing), FixedClock(SERVER_NOW))

    assert not missing.exists()


def test_startup_logs_the_runtime_and_time_data_versions(
    composed: FastAPI, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.INFO, logger=app_module.__name__):
        with TestClient(composed):
            pass

    events = [record.getMessage() for record in caplog.records]
    assert [
        event
        for event in events
        if event.startswith(f"{app_module.STARTUP_EVENT} ")
        and f"runtime={platform.python_version()}" in event
        and "time_data=" in event
    ]


def test_the_route_module_does_not_import_the_composition_module() -> None:
    probe = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys, task_analyzer_server.api;"
            " print('task_analyzer_server.app' in sys.modules)",
        ],
        capture_output=True,
        text=True,
        check=True,
    )

    assert probe.stdout.strip() == "False"


def test_a_successful_response_is_not_cacheable(
    composed: FastAPI, settings: ServerSettings
) -> None:
    operation_id = stored_creation(settings)

    with TestClient(composed) as client:
        response = client.get(f"/v1/operations/{operation_id}")

    assert response.headers["Cache-Control"] == "no-store"


def test_a_protocol_error_response_is_not_cacheable(composed: FastAPI) -> None:
    with TestClient(composed) as client:
        response = client.get("/v1/operations/not-a-uuid")

    assert response.headers["Cache-Control"] == "no-store"


def test_no_route_requires_a_product_credential(
    composed: FastAPI, settings: ServerSettings
) -> None:
    operation_id = stored_creation(settings)

    with TestClient(composed) as client:
        response = client.get(f"/v1/operations/{operation_id}")

    assert response.status_code == 200


def test_a_forwarded_identity_header_is_not_a_product_account(
    composed: FastAPI, settings: ServerSettings
) -> None:
    operation_id = stored_creation(settings)

    with TestClient(composed) as client:
        anonymous = client.get(f"/v1/operations/{operation_id}")
        forwarded = client.get(
            f"/v1/operations/{operation_id}",
            headers=FORWARDED_IDENTITY_HEADERS,
        )

    assert forwarded.status_code == anonymous.status_code
    assert forwarded.json() == anonymous.json()


def test_an_unusable_envelope_is_refused_with_the_exact_contract(
    composed: FastAPI,
) -> None:
    with TestClient(composed) as client:
        response = client.get("/v1/operations/not-a-uuid")
    body = response.json()

    assert response.status_code == 400
    assert body["error"] == {
        "code": ErrorCode.INVALID_OPERATION_ENVELOPE.value,
        "fields": [],
    }
    assert set(body) == PROTOCOL_ERROR_FIELDS
    assert UUID(body["request_id"])


def test_a_reused_operation_identity_names_the_operation(
    composed: FastAPI,
) -> None:
    identity = uuid4()

    @composed.get("/probe/reused/{operation_id}")
    def probe(request: Request, operation_id: str) -> Response:
        api.usable_operation_id(request, operation_id)
        raise services.ProtocolRefusalError(ErrorCode.OPERATION_ID_REUSED)

    with TestClient(composed) as client:
        response = client.get(f"/probe/reused/{identity}")
    body = response.json()

    assert response.status_code == 409
    assert body["error"]["code"] == ErrorCode.OPERATION_ID_REUSED.value
    assert body["operation_id"] == str(identity)
    assert set(body) == PROTOCOL_ERROR_FIELDS_WITH_OPERATION


def test_a_task_command_before_zone_setup_is_refused(
    composed: FastAPI, settings: ServerSettings
) -> None:
    identity = uuid4()

    @composed.get("/probe/create/{operation_id}")
    def probe(request: Request, operation_id: str) -> Response:
        parsed = api.usable_operation_id(request, operation_id)
        return api.published(
            services.create_task(
                settings,
                FixedClock(SERVER_NOW),
                OperationRequest(
                    operation_id=parsed,
                    method="POST",
                    target=TASK_TARGET,
                    payload={"title": TASK_TITLE},
                ),
            ),
            201,
        )

    with TestClient(composed) as client:
        response = client.get(f"/probe/create/{identity}")
    body = response.json()

    assert response.status_code == 409
    assert body["error"]["code"] == ErrorCode.PRODUCT_TIME_ZONE_REQUIRED.value
    assert "outcome" not in body


def test_a_storage_failure_invents_no_terminal_outcome(
    composed: FastAPI, database_path: Path
) -> None:
    with TestClient(composed) as client:
        database_path.unlink()
        response = client.get(f"/v1/operations/{UNKNOWN_OPERATION_ID}")
    body = response.json()

    assert response.status_code == 503
    assert body["error"]["code"] == ErrorCode.STORAGE_UNAVAILABLE.value
    assert "outcome" not in body
    assert "task" not in body


def test_an_unexpected_defect_invents_no_terminal_outcome(
    composed: FastAPI,
) -> None:

    @composed.get("/probe/defect")
    def probe() -> Response:
        raise RuntimeError("an unexpected server defect")

    with TestClient(composed, raise_server_exceptions=False) as client:
        response = client.get("/probe/defect")
    body = response.json()

    assert response.status_code == 500
    assert body["error"]["code"] == ErrorCode.INTERNAL_ERROR.value
    assert "outcome" not in body
    assert "task" not in body


def test_a_protocol_error_matches_its_log_record(
    composed: FastAPI, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.WARNING, logger=api.__name__):
        with TestClient(composed) as client:
            response = client.get("/v1/operations/not-a-uuid")

    logged = [
        record
        for record in caplog.records
        if record.getMessage() == api.PROTOCOL_ERROR_EVENT
    ]
    assert [record.request_id for record in logged] == [
        response.json()["request_id"]
    ]
    assert logged[0].error_code == (ErrorCode.INVALID_OPERATION_ENVELOPE.value)


def test_a_protocol_error_never_echoes_submitted_input(
    composed: FastAPI,
) -> None:
    submitted = "titulo-secreto-do-usuario"

    with TestClient(composed) as client:
        response = client.get(f"/v1/operations/{submitted}")

    assert submitted not in response.text

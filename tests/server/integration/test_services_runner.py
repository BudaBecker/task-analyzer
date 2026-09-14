"""Integration tests for the transactional operation runner.

Covers PCE-37 through PCE-43; REQ-010, REQ-031.

Every test opens a newly allocated temporary database file created by
the explicit initializer. Settings are built for that file directly, so
no test reads ``TASK_ANALYZER_DATABASE_PATH`` or touches any configured
runtime database.
"""

import json
import sqlite3
from datetime import UTC, date, datetime
from pathlib import Path
from uuid import UUID, uuid4

import pytest

from task_analyzer_server import schema, services, storage
from task_analyzer_server.contracts import (
    ErrorCode,
    OperationError,
    OperationRequest,
    OperationResult,
    TaskSnapshot,
)
from task_analyzer_server.domain import title_key
from task_analyzer_server.settings import ServerSettings

BUSY_TIMEOUT_MS = 5000
SHORT_TIMEOUT_MS = 250

TITLE = "Read notes"
EQUIVALENT_TITLE = " READ  NOTES "
DEADLINE = date(2026, 9, 14)
CREATED_AT = datetime(2026, 9, 13, 12, 0, 0, 123456, tzinfo=UTC)
RESOLVED_AT = datetime(2026, 9, 13, 12, 0, 0, 654321, tzinfo=UTC)

CREATE_TARGET = "/v1/tasks"
EDIT_TARGET = "/v1/tasks/20000000-0000-4000-8000-000000000001"

PAYLOAD: dict[str, object] = {
    "title": TITLE,
    "observations": None,
    "deadline": "2026-09-14",
}


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


class RecordingCommand:
    """A command that counts its runs and can write a task.

    Attributes:
        runs: How many times the runner applied this command.
    """

    def __init__(
        self,
        result: OperationResult,
        *,
        task_id: UUID | None = None,
        failure: Exception | None = None,
    ) -> None:
        """Build the command.

        Args:
            result: The terminal result to return when applied.
            task_id: Identity of a task to store, or ``None`` to store
                no task.
            failure: An error to raise instead of returning, or
                ``None`` to return the result.
        """
        self.result = result
        self.task_id = task_id
        self.failure = failure
        self.runs = 0

    def __call__(
        self, connection: sqlite3.Connection, request: OperationRequest
    ) -> OperationResult:
        """Apply the command inside the open write transaction.

        Args:
            connection: Connection holding the write transaction.
            request: The submitted operation.

        Returns:
            The configured terminal result.

        Raises:
            Exception: The configured failure, when one was given.
        """
        self.runs += 1
        if self.failure is not None:
            raise self.failure
        if self.task_id is not None:
            storage.insert_task(
                connection,
                task_id=self.task_id,
                title=TITLE,
                title_key=title_key(TITLE),
                observations=None,
                deadline=DEADLINE,
                created_at=CREATED_AT,
            )
        return self.result


def request_for(
    operation_id: UUID,
    *,
    method: str = "POST",
    target: str = CREATE_TARGET,
    payload: object | None = None,
) -> OperationRequest:
    """Build one submitted operation.

    Args:
        operation_id: Identity of the attempt.
        method: HTTP method of the operation.
        target: Canonical task target path.
        payload: Parsed JSON payload, or ``None`` for the default.

    Returns:
        The submitted operation.
    """
    return OperationRequest(
        operation_id=operation_id,
        method=method,
        target=target,
        payload=dict(PAYLOAD) if payload is None else payload,
    )


def success_for(operation_id: UUID, task_id: UUID) -> OperationResult:
    """Build the terminal result of an accepted creation.

    Args:
        operation_id: Identity of the resolved operation.
        task_id: Identity of the created task.

    Returns:
        The success result.
    """
    return OperationResult(
        operation_id=operation_id,
        outcome="succeeded",
        original_http_status=201,
        task=TaskSnapshot(
            task_id=task_id,
            title=TITLE,
            observations=None,
            deadline=DEADLINE,
            status="pending",
            created_at=CREATED_AT,
            completed_at=None,
        ),
        error=None,
        resolved_at=RESOLVED_AT,
    )


def rejection_for(operation_id: UUID) -> OperationResult:
    """Build the terminal result of a business rejection.

    Args:
        operation_id: Identity of the resolved operation.

    Returns:
        The rejection result.
    """
    return OperationResult(
        operation_id=operation_id,
        outcome="rejected",
        original_http_status=409,
        task=None,
        error=OperationError(
            code=ErrorCode.TASK_UNIQUENESS_CONFLICT,
            fields=(),
            conflicting_task_id=uuid4(),
        ),
        resolved_at=RESOLVED_AT,
    )


def read_tasks(settings: ServerSettings) -> tuple[TaskSnapshot, ...]:
    """Read every managed task through a separate connection.

    Args:
        settings: Settings naming the disposable database.

    Returns:
        The committed managed tasks.
    """
    with storage.open_connection(
        settings.database_path, BUSY_TIMEOUT_MS
    ) as connection:
        return storage.read_tasks(connection)


def test_object_key_order_does_not_change_the_identity() -> None:
    """The same fields in another order are the same attempt."""
    operation_id = uuid4()
    ordered = request_for(
        operation_id, payload={"title": TITLE, "deadline": "2026-09-14"}
    )
    reordered = request_for(
        operation_id, payload={"deadline": "2026-09-14", "title": TITLE}
    )

    assert services.canonical_request(ordered) == services.canonical_request(
        reordered
    )


def test_json_whitespace_does_not_change_the_identity() -> None:
    """Spacing in the submitted JSON is not part of the attempt."""
    operation_id = uuid4()
    compact = json.loads('{"title":"Read notes","deadline":null}')
    spaced = json.loads('{\n  "title" : "Read notes",\n "deadline": null\n}')

    assert services.canonical_request(
        request_for(operation_id, payload=compact)
    ) == services.canonical_request(request_for(operation_id, payload=spaced))


def test_a_changed_field_value_changes_the_identity() -> None:
    """A corrected value makes the request a different one."""
    operation_id = uuid4()
    original = request_for(operation_id)
    corrected = request_for(
        operation_id,
        payload={
            "title": TITLE,
            "observations": None,
            "deadline": "2026-09-15",
        },
    )

    assert services.canonical_request(original) != services.canonical_request(
        corrected
    )


def test_a_changed_target_changes_the_identity() -> None:
    """The task a request targets is part of its identity."""
    operation_id = uuid4()

    assert services.canonical_request(
        request_for(operation_id, method="PUT", target=EDIT_TARGET)
    ) != services.canonical_request(
        request_for(
            operation_id,
            method="PUT",
            target="/v1/tasks/20000000-0000-4000-8000-000000000002",
        )
    )


def test_a_changed_method_changes_the_identity() -> None:
    """Creating and editing are never the same attempt."""
    operation_id = uuid4()

    assert services.canonical_request(
        request_for(operation_id, method="POST")
    ) != services.canonical_request(request_for(operation_id, method="PUT"))


def test_the_identity_names_the_api_version() -> None:
    """The canonical request states the contract version it belongs to."""
    canonical = services.canonical_request(request_for(uuid4()))

    assert canonical.startswith(f"{services.API_VERSION}|POST|/v1/tasks|")


def test_the_identity_keeps_values_before_business_normalization() -> None:
    """Submitted values are compared as submitted, not as compared."""
    canonical = services.canonical_request(
        request_for(uuid4(), payload={"title": EQUIVALENT_TITLE})
    )

    assert EQUIVALENT_TITLE in canonical
    assert title_key(EQUIVALENT_TITLE) not in canonical


def test_a_new_attempt_runs_the_command_and_retains_its_result(
    settings: ServerSettings,
) -> None:
    """A first attempt resolves through the command and is retained."""
    operation_id = uuid4()
    task_id = uuid4()
    command = RecordingCommand(
        success_for(operation_id, task_id), task_id=task_id
    )

    result = services.apply_operation(
        settings, request_for(operation_id), command
    )

    assert command.runs == 1
    assert result == success_for(operation_id, task_id)
    assert services.lookup_operation(settings, operation_id) == result


def test_a_terminal_result_commits_with_its_mutation(
    settings: ServerSettings,
) -> None:
    """The change and its result become durable together."""
    operation_id = uuid4()
    task_id = uuid4()
    command = RecordingCommand(
        success_for(operation_id, task_id), task_id=task_id
    )

    services.apply_operation(settings, request_for(operation_id), command)

    assert [task.task_id for task in read_tasks(settings)] == [task_id]
    assert services.lookup_operation(settings, operation_id) is not None


def test_a_repeated_attempt_returns_the_retained_result(
    settings: ServerSettings,
) -> None:
    """A repetition of one attempt is never applied a second time."""
    operation_id = uuid4()
    task_id = uuid4()
    command = RecordingCommand(
        success_for(operation_id, task_id), task_id=task_id
    )
    original = services.apply_operation(
        settings, request_for(operation_id), command
    )

    repeated = services.apply_operation(
        settings, request_for(operation_id), command
    )

    assert repeated == original
    assert command.runs == 1
    assert [task.task_id for task in read_tasks(settings)] == [task_id]


def test_a_repeated_rejection_returns_the_retained_rejection(
    settings: ServerSettings,
) -> None:
    """A repeated rejected attempt stays the same rejection."""
    operation_id = uuid4()
    command = RecordingCommand(rejection_for(operation_id))
    original = services.apply_operation(
        settings, request_for(operation_id), command
    )

    repeated = services.apply_operation(
        settings, request_for(operation_id), command
    )

    assert repeated == original
    assert repeated.outcome == "rejected"
    assert command.runs == 1


def test_a_reused_identity_with_other_content_is_refused(
    settings: ServerSettings,
) -> None:
    """One identity cannot carry a second, different request."""
    operation_id = uuid4()
    task_id = uuid4()
    command = RecordingCommand(
        success_for(operation_id, task_id), task_id=task_id
    )
    services.apply_operation(settings, request_for(operation_id), command)

    with pytest.raises(services.ProtocolRefusalError) as refusal:
        services.apply_operation(
            settings,
            request_for(operation_id, payload={"title": "Other notes"}),
            command,
        )

    assert refusal.value.code == ErrorCode.OPERATION_ID_REUSED
    assert command.runs == 1


def test_a_refused_reuse_preserves_the_retained_result(
    settings: ServerSettings,
) -> None:
    """The original outcome outlives an attempt to reuse its identity."""
    operation_id = uuid4()
    task_id = uuid4()
    command = RecordingCommand(
        success_for(operation_id, task_id), task_id=task_id
    )
    original = services.apply_operation(
        settings, request_for(operation_id), command
    )

    with pytest.raises(services.ProtocolRefusalError):
        services.apply_operation(
            settings,
            request_for(operation_id, payload={"title": "Other notes"}),
            command,
        )

    assert services.lookup_operation(settings, operation_id) == original


def test_a_refused_reuse_preserves_every_task(
    settings: ServerSettings,
) -> None:
    """A refused reuse changes no task data at all."""
    operation_id = uuid4()
    task_id = uuid4()
    command = RecordingCommand(
        success_for(operation_id, task_id), task_id=task_id
    )
    services.apply_operation(settings, request_for(operation_id), command)
    before = read_tasks(settings)

    with pytest.raises(services.ProtocolRefusalError):
        services.apply_operation(
            settings,
            request_for(operation_id, payload={"title": "Other notes"}),
            command,
        )

    assert read_tasks(settings) == before


def test_the_write_lock_is_taken_before_the_ledger_is_read(
    settings: ServerSettings,
) -> None:
    """A blocked writer cannot even reach a retained replay."""
    operation_id = uuid4()
    command = RecordingCommand(rejection_for(operation_id))
    services.apply_operation(settings, request_for(operation_id), command)
    blocked = ServerSettings(
        database_path=settings.database_path,
        log_level=settings.log_level,
        db_busy_timeout_ms=SHORT_TIMEOUT_MS,
    )

    with storage.open_connection(
        settings.database_path, BUSY_TIMEOUT_MS
    ) as holder:
        with storage.write_transaction(holder):
            with pytest.raises(sqlite3.OperationalError):
                services.apply_operation(
                    blocked, request_for(operation_id), command
                )


def test_an_unexpected_command_failure_establishes_no_outcome(
    settings: ServerSettings,
) -> None:
    """A command that fails leaves nothing terminal behind."""
    operation_id = uuid4()
    command = RecordingCommand(
        success_for(operation_id, uuid4()),
        task_id=uuid4(),
        failure=RuntimeError("injected command failure"),
    )

    with pytest.raises(RuntimeError, match="injected"):
        services.apply_operation(settings, request_for(operation_id), command)

    assert services.lookup_operation(settings, operation_id) is None
    assert read_tasks(settings) == ()


def test_a_failed_commit_is_not_reported_as_persisted(
    settings: ServerSettings, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A commit that fails yields an error, never a success."""
    monkeypatch.setattr(storage, "COMMIT", "COMMIT NOT A STATEMENT")
    operation_id = uuid4()
    task_id = uuid4()
    command = RecordingCommand(
        success_for(operation_id, task_id), task_id=task_id
    )

    with pytest.raises(sqlite3.OperationalError):
        services.apply_operation(settings, request_for(operation_id), command)

    monkeypatch.undo()
    assert services.lookup_operation(settings, operation_id) is None
    assert read_tasks(settings) == ()


def test_lookup_returns_the_retained_outcome(
    settings: ServerSettings,
) -> None:
    """Consulting an established identity returns its outcome."""
    operation_id = uuid4()
    command = RecordingCommand(rejection_for(operation_id))
    original = services.apply_operation(
        settings, request_for(operation_id), command
    )

    assert services.lookup_operation(settings, operation_id) == original


def test_lookup_reports_unknown_for_an_unestablished_identity(
    settings: ServerSettings,
) -> None:
    """An identity with no committed outcome reads as unknown."""
    assert services.lookup_operation(settings, uuid4()) is None


def test_lookup_reads_without_taking_the_write_lock(
    settings: ServerSettings,
) -> None:
    """Consulting an outcome never waits for a writer."""
    operation_id = uuid4()
    command = RecordingCommand(rejection_for(operation_id))
    original = services.apply_operation(
        settings, request_for(operation_id), command
    )

    with storage.open_connection(
        settings.database_path, BUSY_TIMEOUT_MS
    ) as holder:
        with storage.write_transaction(holder):
            consulted = services.lookup_operation(settings, operation_id)

    assert consulted == original


def test_the_runner_applies_any_command_unchanged(
    settings: ServerSettings,
) -> None:
    """The runner carries a command it knows nothing about."""
    created = uuid4()
    first = uuid4()
    services.apply_operation(
        settings,
        request_for(first),
        RecordingCommand(success_for(first, created), task_id=created),
    )
    edited = OperationResult(
        operation_id=uuid4(),
        outcome="succeeded",
        original_http_status=200,
        task=TaskSnapshot(
            task_id=created,
            title="Other notes",
            observations=None,
            deadline=None,
            status="pending",
            created_at=CREATED_AT,
            completed_at=None,
        ),
        error=None,
        resolved_at=RESOLVED_AT,
    )

    def rename(
        connection: sqlite3.Connection, request: OperationRequest
    ) -> OperationResult:
        """Apply an unrelated command through the same runner.

        Args:
            connection: Connection holding the write transaction.
            request: The submitted operation.

        Returns:
            The terminal result of the rename.
        """
        storage.update_task(
            connection,
            task_id=created,
            title="Other notes",
            title_key=title_key("Other notes"),
            observations=None,
            deadline=None,
        )
        return edited

    result = services.apply_operation(
        settings,
        request_for(edited.operation_id, method="PUT", target=EDIT_TARGET),
        rename,
    )

    assert result == edited
    assert [task.title for task in read_tasks(settings)] == ["Other notes"]

"""Integration tests for the task creation command.

Covers PCE-01 through PCE-10, PCE-28, PCE-37, PCE-48, PCE-51, PCE-52;
REQ-007, REQ-008, REQ-010, REQ-028.

Every test opens a newly allocated temporary database file created by
the explicit initializer. Settings are built for that file directly, so
no test reads ``TASK_ANALYZER_DATABASE_PATH`` or touches any configured
runtime database.

Every boundary is exercised with plain text and with combined
characters, so an implementation counting code points or bytes instead
of user-perceived characters fails these tests. Characters that would be
invisible in source are built from their code points on purpose.
"""

from datetime import UTC, date, datetime
from pathlib import Path
from uuid import UUID, uuid4

import pytest

from task_analyzer_server import schema, services, storage
from task_analyzer_server.contracts import (
    DEADLINE_FIELD,
    OBSERVATIONS_FIELD,
    TITLE_FIELD,
    ErrorCode,
    FieldErrorCode,
    OperationRequest,
    OperationResult,
    TaskSnapshot,
    ValidationIssue,
)
from task_analyzer_server.domain import title_key
from task_analyzer_server.settings import ServerSettings

BUSY_TIMEOUT_MS = 5000

PRODUCT_ZONE = "America/Sao_Paulo"
SERVER_NOW = datetime(2026, 9, 14, 2, 30, 0, 123456, tzinfo=UTC)

CREATE_TARGET = "/v1/tasks"
TITLE = "Read notes"

COMBINING_ACUTE = chr(0x0301)
ZERO_WIDTH_JOINER = chr(0x200D)

COMBINING_E = "e" + COMBINING_ACUTE
"""One user-perceived character: base letter plus a combining acute."""

JOINED_FAMILY = ZERO_WIDTH_JOINER.join(
    ("\U0001f468", "\U0001f469", "\U0001f467", "\U0001f466")
)
"""One user-perceived character: a zero-width-joined emoji sequence."""

TOO_LONG_TITLE = ValidationIssue(
    field=TITLE_FIELD, code=FieldErrorCode.TITLE_TOO_LONG
)
REQUIRED_TITLE = ValidationIssue(
    field=TITLE_FIELD, code=FieldErrorCode.TITLE_REQUIRED
)
TOO_LONG_OBSERVATIONS = ValidationIssue(
    field=OBSERVATIONS_FIELD, code=FieldErrorCode.OBSERVATIONS_TOO_LONG
)
INVALID_DEADLINE = ValidationIssue(
    field=DEADLINE_FIELD, code=FieldErrorCode.INVALID_DEADLINE
)


class FixedClock:
    """A clock reporting one instant."""

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
    """Build settings for a configured disposable database.

    Args:
        tmp_path: pytest-allocated temporary directory.

    Returns:
        Settings naming the newly created database file, with the
        product time zone already fixed.
    """
    path = tmp_path / "disposable.sqlite3"
    schema.initialize_database(path)
    configured = ServerSettings(
        database_path=path,
        log_level="INFO",
        db_busy_timeout_ms=BUSY_TIMEOUT_MS,
    )
    services.configure_zone(configured, FixedClock(), PRODUCT_ZONE)
    return configured


def creation_request(
    title: str = TITLE,
    observations: str | None = None,
    deadline: str | None = None,
    operation_id: UUID | None = None,
) -> OperationRequest:
    """Build one submitted creation operation.

    Args:
        title: Submitted title text.
        observations: Submitted observations, or ``None``.
        deadline: Submitted calendar-date text, or ``None``.
        operation_id: Identity of the attempt, or ``None`` for a new one.

    Returns:
        The submitted operation.
    """
    return OperationRequest(
        operation_id=uuid4() if operation_id is None else operation_id,
        method="POST",
        target=CREATE_TARGET,
        payload={
            "title": title,
            "observations": observations,
            "deadline": deadline,
        },
    )


def create(
    settings: ServerSettings,
    title: str = TITLE,
    observations: str | None = None,
    deadline: str | None = None,
) -> OperationResult:
    """Run one creation through the command under test.

    Args:
        settings: Settings naming the configured disposable database.
        title: Submitted title text.
        observations: Submitted observations, or ``None``.
        deadline: Submitted calendar-date text, or ``None``.

    Returns:
        The terminal result of the attempt.
    """
    return services.create_task(
        settings,
        FixedClock(),
        creation_request(title, observations, deadline),
    )


def stored_tasks(settings: ServerSettings) -> tuple[TaskSnapshot, ...]:
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


def test_a_title_only_creation_produces_a_pending_task(
    settings: ServerSettings,
) -> None:
    """A title alone is enough to retain a task."""
    result = create(settings)

    assert result.outcome == "succeeded"
    assert result.original_http_status == 201
    assert result.task is not None
    assert result.task.title == TITLE
    assert result.task.observations is None
    assert result.task.deadline is None
    assert result.task.status == "pending"
    assert result.task.completed_at is None


def test_optional_values_persist_exactly_as_supplied(
    settings: ServerSettings,
) -> None:
    """Observations and a deadline are retained as submitted."""
    create(settings, observations="Bring the folder", deadline="2026-09-14")

    stored = stored_tasks(settings)
    assert len(stored) == 1
    assert stored[0].observations == "Bring the folder"
    assert stored[0].deadline == date(2026, 9, 14)


def test_line_breaks_in_observations_are_retained(
    settings: ServerSettings,
) -> None:
    """Multiline observations keep every line break."""
    observations = "First line\nSecond line\n\nFourth line"

    create(settings, observations=observations)

    assert stored_tasks(settings)[0].observations == observations


def test_a_past_deadline_is_accepted(
    settings: ServerSettings,
) -> None:
    """A deadline before the current product date is still valid."""
    result = create(settings, deadline="2020-01-31")

    assert result.outcome == "succeeded"
    assert stored_tasks(settings)[0].deadline == date(2020, 1, 31)


def test_the_earliest_supported_deadline_is_accepted(
    settings: ServerSettings,
) -> None:
    """The supported range starts at 0001-01-01."""
    result = create(settings, deadline="0001-01-01")

    assert result.outcome == "succeeded"
    assert stored_tasks(settings)[0].deadline == date(1, 1, 1)


def test_the_latest_supported_deadline_is_accepted(
    settings: ServerSettings,
) -> None:
    """The supported range ends at 9999-12-30."""
    result = create(settings, deadline="9999-12-30")

    assert result.outcome == "succeeded"
    assert stored_tasks(settings)[0].deadline == date(9999, 12, 30)


def test_a_deadline_past_the_supported_range_is_rejected(
    settings: ServerSettings,
) -> None:
    """9999-12-31 is outside the approved range."""
    result = create(settings, deadline="9999-12-31")

    assert result.outcome == "rejected"
    assert result.original_http_status == 422
    assert result.error is not None
    assert result.error.code == ErrorCode.TASK_VALIDATION_FAILED
    assert result.error.fields == (INVALID_DEADLINE,)
    assert stored_tasks(settings) == ()


def test_an_invalid_calendar_date_is_rejected(
    settings: ServerSettings,
) -> None:
    """A date the calendar does not have is not a deadline."""
    result = create(settings, deadline="2026-02-30")

    assert result.outcome == "rejected"
    assert result.error is not None
    assert result.error.fields == (INVALID_DEADLINE,)
    assert stored_tasks(settings) == ()


def test_an_empty_title_is_rejected(
    settings: ServerSettings,
) -> None:
    """A task always needs a title."""
    result = create(settings, title="")

    assert result.outcome == "rejected"
    assert result.error is not None
    assert result.error.fields == (REQUIRED_TITLE,)
    assert stored_tasks(settings) == ()


def test_a_whitespace_only_title_is_rejected(
    settings: ServerSettings,
) -> None:
    """Spaces alone do not make a title."""
    result = create(settings, title="   ")

    assert result.outcome == "rejected"
    assert result.error is not None
    assert result.error.fields == (REQUIRED_TITLE,)
    assert stored_tasks(settings) == ()


def test_a_title_of_two_hundred_characters_is_accepted(
    settings: ServerSettings,
) -> None:
    """Exactly 200 characters after trimming is within the limit."""
    result = create(settings, title="a" * 200)

    assert result.outcome == "succeeded"
    assert stored_tasks(settings)[0].title == "a" * 200


def test_a_title_of_two_hundred_and_one_characters_is_rejected(
    settings: ServerSettings,
) -> None:
    """One character past the limit is rejected."""
    result = create(settings, title="a" * 201)

    assert result.outcome == "rejected"
    assert result.error is not None
    assert result.error.fields == (TOO_LONG_TITLE,)
    assert stored_tasks(settings) == ()


def test_a_title_is_measured_after_trimming_edge_spaces(
    settings: ServerSettings,
) -> None:
    """Edge spaces do not count towards the title limit."""
    result = create(settings, title="  " + "a" * 200 + "  ")

    assert result.outcome == "succeeded"
    assert stored_tasks(settings)[0].title == "  " + "a" * 200 + "  "


def test_two_hundred_combined_characters_are_accepted(
    settings: ServerSettings,
) -> None:
    """A combining sequence counts as one character, not two."""
    result = create(settings, title=COMBINING_E * 200)

    assert result.outcome == "succeeded"
    assert stored_tasks(settings)[0].title == COMBINING_E * 200


def test_two_hundred_and_one_combined_characters_are_rejected(
    settings: ServerSettings,
) -> None:
    """The limit applies to user-perceived characters."""
    result = create(settings, title=COMBINING_E * 201)

    assert result.outcome == "rejected"
    assert result.error is not None
    assert result.error.fields == (TOO_LONG_TITLE,)
    assert stored_tasks(settings) == ()


def test_two_hundred_joined_emoji_are_accepted(
    settings: ServerSettings,
) -> None:
    """A joined emoji sequence counts as one character."""
    result = create(settings, title=JOINED_FAMILY * 200)

    assert result.outcome == "succeeded"
    assert stored_tasks(settings)[0].title == JOINED_FAMILY * 200


def test_two_hundred_and_one_joined_emoji_are_rejected(
    settings: ServerSettings,
) -> None:
    """Joined emoji are counted the same way at the boundary."""
    result = create(settings, title=JOINED_FAMILY * 201)

    assert result.outcome == "rejected"
    assert result.error is not None
    assert result.error.fields == (TOO_LONG_TITLE,)
    assert stored_tasks(settings) == ()


def test_five_thousand_observation_characters_are_accepted(
    settings: ServerSettings,
) -> None:
    """Exactly 5,000 characters of observations is within the limit."""
    result = create(settings, observations="a" * 5000)

    assert result.outcome == "succeeded"
    assert stored_tasks(settings)[0].observations == "a" * 5000


def test_five_thousand_and_one_observation_characters_are_rejected(
    settings: ServerSettings,
) -> None:
    """One character past the observation limit is rejected."""
    result = create(settings, observations="a" * 5001)

    assert result.outcome == "rejected"
    assert result.error is not None
    assert result.error.fields == (TOO_LONG_OBSERVATIONS,)
    assert stored_tasks(settings) == ()


def test_five_thousand_combined_observation_characters_are_accepted(
    settings: ServerSettings,
) -> None:
    """Observations are counted in user-perceived characters too."""
    result = create(settings, observations=COMBINING_E * 5000)

    assert result.outcome == "succeeded"
    assert stored_tasks(settings)[0].observations == COMBINING_E * 5000


def test_five_thousand_and_one_combined_characters_are_rejected(
    settings: ServerSettings,
) -> None:
    """The observation limit holds at the combined-character boundary."""
    result = create(settings, observations=COMBINING_E * 5001)

    assert result.outcome == "rejected"
    assert result.error is not None
    assert result.error.fields == (TOO_LONG_OBSERVATIONS,)
    assert stored_tasks(settings) == ()


def test_an_unexpected_field_is_rejected(
    settings: ServerSettings,
) -> None:
    """A server-owned field is refused, never silently applied."""
    request = OperationRequest(
        operation_id=uuid4(),
        method="POST",
        target=CREATE_TARGET,
        payload={"title": TITLE, "status": "completed"},
    )

    result = services.create_task(settings, FixedClock(), request)

    assert result.outcome == "rejected"
    assert result.error is not None
    assert result.error.fields == (
        ValidationIssue(field="status", code=FieldErrorCode.UNEXPECTED_FIELD),
    )
    assert stored_tasks(settings) == ()


def test_the_creation_instant_comes_from_the_server_clock(
    settings: ServerSettings,
) -> None:
    """The original creation time is the server's own instant."""
    result = create(settings)

    assert result.task is not None
    assert result.task.created_at == SERVER_NOW
    assert stored_tasks(settings)[0].created_at == SERVER_NOW


def test_the_task_receives_a_server_generated_identity(
    settings: ServerSettings,
) -> None:
    """Identity is assigned by the server, never by the title."""
    first = create(settings, title="Read notes")
    second = create(settings, title="Read other notes")

    assert first.task is not None
    assert second.task is not None
    assert first.task.task_id != second.task.task_id
    assert {task.task_id for task in stored_tasks(settings)} == {
        first.task.task_id,
        second.task.task_id,
    }


def test_a_rejection_retains_its_result_without_a_task(
    settings: ServerSettings,
) -> None:
    """A rejected creation is durable evidence, not a task."""
    request = creation_request(title="")

    result = services.create_task(settings, FixedClock(), request)

    assert services.lookup_operation(settings, request.operation_id) == (
        result
    )
    assert stored_tasks(settings) == ()


def test_success_is_reported_only_from_committed_state(
    settings: ServerSettings,
) -> None:
    """The reported task is the one a later reader finds."""
    result = create(settings, observations="Bring the folder")

    assert result.task is not None
    assert stored_tasks(settings) == (result.task,)
    assert services.lookup_operation(settings, result.operation_id) == (result)


def test_a_repeated_creation_creates_no_second_task(
    settings: ServerSettings,
) -> None:
    """Repeating one attempt returns the original single task."""
    request = creation_request()
    original = services.create_task(settings, FixedClock(), request)

    repeated = services.create_task(settings, FixedClock(), request)

    assert repeated == original
    assert len(stored_tasks(settings)) == 1


def test_the_stored_comparison_key_is_the_central_derivation(
    settings: ServerSettings,
) -> None:
    """The stored key comes from the one title-key derivation."""
    submitted = " READ  NOTES "

    create(settings, title=submitted)

    with storage.open_connection(
        settings.database_path, BUSY_TIMEOUT_MS
    ) as connection:
        row = connection.execute(
            "SELECT title, title_key FROM tasks"
        ).fetchone()

    assert row[0] == submitted
    assert row[1] == title_key(submitted)


def test_creation_is_refused_before_the_product_zone_is_fixed(
    tmp_path: Path,
) -> None:
    """An unconfigured server records no terminal task result."""
    path = tmp_path / "unconfigured.sqlite3"
    schema.initialize_database(path)
    unconfigured = ServerSettings(
        database_path=path,
        log_level="INFO",
        db_busy_timeout_ms=BUSY_TIMEOUT_MS,
    )
    request = creation_request()

    with pytest.raises(services.ProtocolRefusalError) as refusal:
        services.create_task(unconfigured, FixedClock(), request)

    assert refusal.value.code == ErrorCode.PRODUCT_TIME_ZONE_REQUIRED
    assert services.lookup_operation(unconfigured, request.operation_id) is (
        None
    )
    assert stored_tasks(unconfigured) == ()

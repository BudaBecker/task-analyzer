"""Integration tests for fixed product zone configuration.

Covers PCE-29, PCE-30, PCE-31, PCE-35; REQ-028.

Every test opens a newly allocated temporary database file created by
the explicit initializer. Settings are built for that file directly, so
no test reads ``TASK_ANALYZER_DATABASE_PATH`` or touches any configured
runtime database.
"""

from datetime import UTC, date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from task_analyzer_server import schema, services, storage
from task_analyzer_server.contracts import ErrorCode
from task_analyzer_server.settings import ServerSettings

BUSY_TIMEOUT_MS = 5000

PRODUCT_ZONE = "America/Sao_Paulo"
ANOTHER_ZONE = "Asia/Tokyo"
UNKNOWN_ZONE = "Nowhere/Nothing"

SERVER_NOW = datetime(2026, 9, 14, 2, 30, 0, 123456, tzinfo=UTC)
PRODUCT_DATE_IN_SAO_PAULO = date(2026, 9, 13)
PRODUCT_DATE_IN_TOKYO = date(2026, 9, 14)

COUNT_LEDGER_ROWS = "SELECT COUNT(*) FROM operation_results"


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


def retained_zone(settings: ServerSettings) -> str | None:
    """Read the retained zone through a separate new connection.

    Args:
        settings: Settings naming the disposable database.

    Returns:
        The retained IANA key, or ``None`` while unset.
    """
    with storage.open_connection(
        settings.database_path, BUSY_TIMEOUT_MS
    ) as connection:
        return storage.read_product_time_zone(connection)


def ledger_rows(settings: ServerSettings) -> int:
    """Count the retained operation results.

    Args:
        settings: Settings naming the disposable database.

    Returns:
        How many operation results are retained.
    """
    with storage.open_connection(
        settings.database_path, BUSY_TIMEOUT_MS
    ) as connection:
        return int(connection.execute(COUNT_LEDGER_ROWS).fetchone()[0])


def test_an_unknown_zone_key_is_refused(
    settings: ServerSettings,
) -> None:
    """A key the zone database does not know is not a configuration."""
    with pytest.raises(services.ProtocolRefusalError) as refusal:
        services.configure_zone(settings, FixedClock(), UNKNOWN_ZONE)

    assert refusal.value.code == ErrorCode.INVALID_TIME_ZONE


def test_an_unknown_zone_key_stores_nothing(
    settings: ServerSettings,
) -> None:
    """A refused key leaves the singleton unset."""
    with pytest.raises(services.ProtocolRefusalError):
        services.configure_zone(settings, FixedClock(), UNKNOWN_ZONE)

    assert retained_zone(settings) is None


def test_an_empty_zone_key_is_refused(
    settings: ServerSettings,
) -> None:
    """A key that names no zone at all is refused the same way."""
    with pytest.raises(services.ProtocolRefusalError) as refusal:
        services.configure_zone(settings, FixedClock(), "")

    assert refusal.value.code == ErrorCode.INVALID_TIME_ZONE
    assert retained_zone(settings) is None


def test_the_first_setup_persists_the_zone(
    settings: ServerSettings,
) -> None:
    """The first valid setup fixes the product time zone."""
    view = services.configure_zone(settings, FixedClock(), PRODUCT_ZONE)

    assert view.configured is True
    assert view.product_time_zone == PRODUCT_ZONE
    assert retained_zone(settings) == PRODUCT_ZONE


def test_the_view_reports_server_time_and_the_product_date(
    settings: ServerSettings,
) -> None:
    """The product date is server time read in the retained zone."""
    view = services.configure_zone(settings, FixedClock(), PRODUCT_ZONE)

    assert view.server_now == SERVER_NOW
    assert view.product_date == PRODUCT_DATE_IN_SAO_PAULO


def test_the_product_date_follows_the_retained_zone(
    settings: ServerSettings,
) -> None:
    """A different retained zone reads the same instant differently."""
    view = services.configure_zone(settings, FixedClock(), ANOTHER_ZONE)

    assert view.product_date == PRODUCT_DATE_IN_TOKYO


def test_repeating_the_same_key_returns_the_same_configuration(
    settings: ServerSettings,
) -> None:
    """Repeating setup with the retained key is safe and idempotent."""
    first = services.configure_zone(settings, FixedClock(), PRODUCT_ZONE)

    repeated = services.configure_zone(settings, FixedClock(), PRODUCT_ZONE)

    assert repeated == first
    assert retained_zone(settings) == PRODUCT_ZONE


def test_a_different_key_is_refused_as_already_fixed(
    settings: ServerSettings,
) -> None:
    """A second, different key cannot take over the product zone."""
    services.configure_zone(settings, FixedClock(), PRODUCT_ZONE)

    with pytest.raises(services.ProtocolRefusalError) as refusal:
        services.configure_zone(settings, FixedClock(), ANOTHER_ZONE)

    assert refusal.value.code == ErrorCode.PRODUCT_TIME_ZONE_FIXED


def test_a_refused_key_leaves_the_retained_zone_unchanged(
    settings: ServerSettings,
) -> None:
    """The retained zone survives an attempt to replace it."""
    services.configure_zone(settings, FixedClock(), PRODUCT_ZONE)

    with pytest.raises(services.ProtocolRefusalError):
        services.configure_zone(settings, FixedClock(), ANOTHER_ZONE)

    assert retained_zone(settings) == PRODUCT_ZONE
    assert (
        services.configure_zone(
            settings, FixedClock(), PRODUCT_ZONE
        ).product_time_zone
        == PRODUCT_ZONE
    )


def test_setup_records_no_operation_result(
    settings: ServerSettings,
) -> None:
    """Configuration is a compare-and-set, not a durable operation."""
    services.configure_zone(settings, FixedClock(), PRODUCT_ZONE)
    services.configure_zone(settings, FixedClock(), PRODUCT_ZONE)
    with pytest.raises(services.ProtocolRefusalError):
        services.configure_zone(settings, FixedClock(), ANOTHER_ZONE)

    assert ledger_rows(settings) == 0


def test_the_retained_zone_survives_reopening_the_database(
    settings: ServerSettings,
) -> None:
    """A restart finds the configured zone exactly as it was left."""
    services.configure_zone(settings, FixedClock(), PRODUCT_ZONE)

    reopened = services.configure_zone(settings, FixedClock(), PRODUCT_ZONE)

    assert retained_zone(settings) == PRODUCT_ZONE
    assert reopened.product_date == PRODUCT_DATE_IN_SAO_PAULO


def test_a_client_in_another_zone_does_not_move_the_product_date(
    settings: ServerSettings,
) -> None:
    """The same instant in another representation reads identically."""
    services.configure_zone(settings, FixedClock(), PRODUCT_ZONE)
    elsewhere = FixedClock(SERVER_NOW.astimezone(ZoneInfo(ANOTHER_ZONE)))

    view = services.configure_zone(settings, elsewhere, PRODUCT_ZONE)

    assert view.server_now == SERVER_NOW
    assert view.product_date == PRODUCT_DATE_IN_SAO_PAULO


def test_a_client_in_another_zone_cannot_replace_the_zone(
    settings: ServerSettings,
) -> None:
    """A desktop that moved cannot reconfigure the product zone."""
    services.configure_zone(settings, FixedClock(), PRODUCT_ZONE)
    elsewhere = FixedClock(SERVER_NOW.astimezone(ZoneInfo(ANOTHER_ZONE)))

    with pytest.raises(services.ProtocolRefusalError):
        services.configure_zone(settings, elsewhere, ANOTHER_ZONE)

    assert retained_zone(settings) == PRODUCT_ZONE


def test_a_task_command_is_refused_before_setup(
    settings: ServerSettings,
) -> None:
    """An unconfigured server refuses task work without an outcome."""
    with storage.open_connection(
        settings.database_path, BUSY_TIMEOUT_MS
    ) as connection:
        with pytest.raises(services.ProtocolRefusalError) as refusal:
            services.require_product_time_zone(connection)

    assert refusal.value.code == ErrorCode.PRODUCT_TIME_ZONE_REQUIRED
    assert ledger_rows(settings) == 0


def test_a_task_command_finds_the_retained_zone_after_setup(
    settings: ServerSettings,
) -> None:
    """Once fixed, the zone is what task commands read."""
    services.configure_zone(settings, FixedClock(), PRODUCT_ZONE)

    with storage.open_connection(
        settings.database_path, BUSY_TIMEOUT_MS
    ) as connection:
        required = services.require_product_time_zone(connection)

    assert required == PRODUCT_ZONE

"""End-to-end tests for the product configuration routes.

Covers PCE-29, PCE-30, PCE-31, PCE-35; REQ-028.

Every test composes the real application against a newly allocated
temporary database created by the explicit initializer, so no test
reaches any configured runtime database.
"""

from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from task_analyzer_server import app as app_module
from task_analyzer_server import schema, services, storage
from task_analyzer_server.contracts import ErrorCode
from task_analyzer_server.settings import ServerSettings

BUSY_TIMEOUT_MS = 5000

PRODUCT_ZONE = "America/Sao_Paulo"
ANOTHER_ZONE = "Asia/Tokyo"
UNKNOWN_ZONE = "Nowhere/Nothing"

SERVER_NOW = datetime(2026, 9, 14, 2, 30, 0, 123456, tzinfo=UTC)
SERVER_NOW_TEXT = "2026-09-14T02:30:00.123456Z"
PRODUCT_DATE_IN_SAO_PAULO = "2026-09-13"

CONFIGURATION_ROUTE = "/v1/configuration"

CONFIGURATION_FIELDS = frozenset(
    {"configured", "product_time_zone", "server_now", "product_date"}
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


@pytest.fixture
def composed(settings: ServerSettings) -> FastAPI:
    """Compose the real application for the disposable database.

    Args:
        settings: Settings naming the disposable database.

    Returns:
        The composed application, not yet started.
    """
    return app_module.create_app(settings, FixedClock())


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


def test_an_unconfigured_server_reports_no_zone(composed: FastAPI) -> None:
    """Before setup the configuration reports its own absence."""
    with TestClient(composed) as client:
        response = client.get(CONFIGURATION_ROUTE)
    body = response.json()

    assert response.status_code == 200
    assert body["configured"] is False
    assert body["product_time_zone"] is None
    assert body["product_date"] is None
    assert body["server_now"] == SERVER_NOW_TEXT


def test_the_configuration_publishes_exactly_its_approved_fields(
    composed: FastAPI,
) -> None:
    """The configuration view carries the approved fields and no more."""
    with TestClient(composed) as client:
        body = client.get(CONFIGURATION_ROUTE).json()

    assert set(body) == CONFIGURATION_FIELDS


def test_a_configured_server_reports_the_retained_zone(
    composed: FastAPI, settings: ServerSettings
) -> None:
    """After setup the configuration reports the fixed zone."""
    services.configure_zone(settings, FixedClock(), PRODUCT_ZONE)

    with TestClient(composed) as client:
        body = client.get(CONFIGURATION_ROUTE).json()

    assert body["configured"] is True
    assert body["product_time_zone"] == PRODUCT_ZONE


def test_the_product_date_is_read_in_the_retained_zone(
    composed: FastAPI, settings: ServerSettings
) -> None:
    """The product date follows the fixed zone, not the host's."""
    services.configure_zone(settings, FixedClock(), PRODUCT_ZONE)

    with TestClient(composed) as client:
        body = client.get(CONFIGURATION_ROUTE).json()

    assert body["server_now"] == SERVER_NOW_TEXT
    assert body["product_date"] == PRODUCT_DATE_IN_SAO_PAULO


def test_the_first_valid_setup_is_accepted(composed: FastAPI) -> None:
    """Setup answers with the configuration it just fixed."""
    with TestClient(composed) as client:
        response = client.put(
            CONFIGURATION_ROUTE, json={"product_time_zone": PRODUCT_ZONE}
        )
    body = response.json()

    assert response.status_code == 200
    assert body["configured"] is True
    assert body["product_time_zone"] == PRODUCT_ZONE
    assert body["product_date"] == PRODUCT_DATE_IN_SAO_PAULO


def test_the_first_valid_setup_is_persisted(
    composed: FastAPI, settings: ServerSettings
) -> None:
    """The fixed zone is retained, not only reported."""
    with TestClient(composed) as client:
        client.put(
            CONFIGURATION_ROUTE, json={"product_time_zone": PRODUCT_ZONE}
        )
        read_back = client.get(CONFIGURATION_ROUTE).json()

    assert retained_zone(settings) == PRODUCT_ZONE
    assert read_back["product_time_zone"] == PRODUCT_ZONE


def test_repeating_the_same_setup_returns_the_same_configuration(
    composed: FastAPI,
) -> None:
    """The same key is safe to send again."""
    with TestClient(composed) as client:
        first = client.put(
            CONFIGURATION_ROUTE, json={"product_time_zone": PRODUCT_ZONE}
        )
        second = client.put(
            CONFIGURATION_ROUTE, json={"product_time_zone": PRODUCT_ZONE}
        )

    assert second.status_code == 200
    assert second.json() == first.json()


def test_a_different_key_is_refused(composed: FastAPI) -> None:
    """A second, different key conflicts with the fixed zone."""
    with TestClient(composed) as client:
        client.put(
            CONFIGURATION_ROUTE, json={"product_time_zone": PRODUCT_ZONE}
        )
        response = client.put(
            CONFIGURATION_ROUTE, json={"product_time_zone": ANOTHER_ZONE}
        )
    body = response.json()

    assert response.status_code == 409
    assert body["error"]["code"] == ErrorCode.PRODUCT_TIME_ZONE_FIXED.value


def test_a_different_key_does_not_replace_the_retained_zone(
    composed: FastAPI, settings: ServerSettings
) -> None:
    """A refused key leaves the fixed zone exactly as it was."""
    with TestClient(composed) as client:
        client.put(
            CONFIGURATION_ROUTE, json={"product_time_zone": PRODUCT_ZONE}
        )
        client.put(
            CONFIGURATION_ROUTE, json={"product_time_zone": ANOTHER_ZONE}
        )
        read_back = client.get(CONFIGURATION_ROUTE).json()

    assert retained_zone(settings) == PRODUCT_ZONE
    assert read_back["product_time_zone"] == PRODUCT_ZONE


def test_an_unknown_zone_is_refused(composed: FastAPI) -> None:
    """A key the server's zone data does not know is not a zone."""
    with TestClient(composed) as client:
        response = client.put(
            CONFIGURATION_ROUTE, json={"product_time_zone": UNKNOWN_ZONE}
        )
    body = response.json()

    assert response.status_code == 422
    assert body["error"]["code"] == ErrorCode.INVALID_TIME_ZONE.value


def test_an_unknown_zone_configures_nothing(
    composed: FastAPI, settings: ServerSettings
) -> None:
    """A refused key leaves the server unconfigured."""
    with TestClient(composed) as client:
        client.put(
            CONFIGURATION_ROUTE, json={"product_time_zone": UNKNOWN_ZONE}
        )
        read_back = client.get(CONFIGURATION_ROUTE).json()

    assert retained_zone(settings) is None
    assert read_back["configured"] is False


def test_a_body_without_a_usable_zone_key_is_refused(
    composed: FastAPI,
) -> None:
    """A setup carrying no usable key configures nothing."""
    with TestClient(composed) as client:
        missing = client.put(CONFIGURATION_ROUTE, json={})
        wrong_type = client.put(
            CONFIGURATION_ROUTE, json={"product_time_zone": 7}
        )

    assert missing.status_code == 422
    assert missing.json()["error"]["code"] == ErrorCode.INVALID_TIME_ZONE.value
    assert wrong_type.status_code == 422


def test_an_unparseable_setup_body_is_refused(composed: FastAPI) -> None:
    """A body that is not JSON leaves the server unconfigured."""
    with TestClient(composed) as client:
        response = client.put(CONFIGURATION_ROUTE, content=b"{not json")
        read_back = client.get(CONFIGURATION_ROUTE).json()

    assert response.status_code == 422
    assert (
        response.json()["error"]["code"] == ErrorCode.INVALID_TIME_ZONE.value
    )
    assert read_back["configured"] is False


def test_reading_the_configuration_is_not_cacheable(
    composed: FastAPI,
) -> None:
    """A configuration read always reaches the server."""
    with TestClient(composed) as client:
        response = client.get(CONFIGURATION_ROUTE)

    assert response.headers["Cache-Control"] == "no-store"


def test_configuring_the_zone_is_not_cacheable(composed: FastAPI) -> None:
    """A setup answer is not cacheable either."""
    with TestClient(composed) as client:
        response = client.put(
            CONFIGURATION_ROUTE, json={"product_time_zone": PRODUCT_ZONE}
        )

    assert response.headers["Cache-Control"] == "no-store"

"""End-to-end tests for the product configuration routes.

Covers PCE-29, PCE-30, PCE-31, PCE-35; REQ-028.
"""

from datetime import UTC, datetime

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from helpers import FixedClock

from task_analyzer_server import app as app_module
from task_analyzer_server import services, storage
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


@pytest.fixture
def composed(settings: ServerSettings) -> FastAPI:
    return app_module.create_app(settings, FixedClock(SERVER_NOW))


def retained_zone(settings: ServerSettings) -> str | None:
    with storage.open_connection(
        settings.database_path, BUSY_TIMEOUT_MS
    ) as connection:
        return storage.read_product_time_zone(connection)


def test_an_unconfigured_server_reports_no_zone(composed: FastAPI) -> None:
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
    with TestClient(composed) as client:
        body = client.get(CONFIGURATION_ROUTE).json()

    assert set(body) == CONFIGURATION_FIELDS


def test_a_configured_server_reports_the_retained_zone(
    composed: FastAPI, settings: ServerSettings
) -> None:
    services.configure_zone(settings, FixedClock(SERVER_NOW), PRODUCT_ZONE)

    with TestClient(composed) as client:
        body = client.get(CONFIGURATION_ROUTE).json()

    assert body["configured"] is True
    assert body["product_time_zone"] == PRODUCT_ZONE


def test_the_product_date_is_read_in_the_retained_zone(
    composed: FastAPI, settings: ServerSettings
) -> None:
    services.configure_zone(settings, FixedClock(SERVER_NOW), PRODUCT_ZONE)

    with TestClient(composed) as client:
        body = client.get(CONFIGURATION_ROUTE).json()

    assert body["server_now"] == SERVER_NOW_TEXT
    assert body["product_date"] == PRODUCT_DATE_IN_SAO_PAULO


def test_the_first_valid_setup_is_accepted(composed: FastAPI) -> None:
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
    with TestClient(composed) as client:
        missing = client.put(CONFIGURATION_ROUTE, json={})
        wrong_type = client.put(
            CONFIGURATION_ROUTE, json={"product_time_zone": 7}
        )

    assert missing.status_code == 422
    assert missing.json()["error"]["code"] == ErrorCode.INVALID_TIME_ZONE.value
    assert wrong_type.status_code == 422


def test_an_unparseable_setup_body_is_refused(composed: FastAPI) -> None:
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
    with TestClient(composed) as client:
        response = client.get(CONFIGURATION_ROUTE)

    assert response.headers["Cache-Control"] == "no-store"


def test_configuring_the_zone_is_not_cacheable(composed: FastAPI) -> None:
    with TestClient(composed) as client:
        response = client.put(
            CONFIGURATION_ROUTE, json={"product_time_zone": PRODUCT_ZONE}
        )

    assert response.headers["Cache-Control"] == "no-store"

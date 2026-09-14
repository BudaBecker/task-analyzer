"""Unit tests for validated runtime settings.

Covers PCE-44 and PCE-45; REQ-003.
"""

from pathlib import Path

import pytest

from task_analyzer_server.settings import (
    DATABASE_PATH_VARIABLE,
    DB_BUSY_TIMEOUT_VARIABLE,
    LOG_LEVEL_VARIABLE,
    ServerSettings,
    SettingsError,
)


def disposable_environment(tmp_path: Path) -> dict[str, str]:
    return {DATABASE_PATH_VARIABLE: str(tmp_path / "disposable.sqlite3")}


def test_missing_database_path_is_rejected() -> None:
    with pytest.raises(SettingsError) as failure:
        ServerSettings.from_environment({})

    assert DATABASE_PATH_VARIABLE in str(failure.value)


def test_relative_database_path_is_rejected() -> None:
    environment = {DATABASE_PATH_VARIABLE: "data/task-analyzer.sqlite3"}

    with pytest.raises(SettingsError) as failure:
        ServerSettings.from_environment(environment)

    assert DATABASE_PATH_VARIABLE in str(failure.value)


def test_absolute_database_path_is_accepted(tmp_path: Path) -> None:
    expected = tmp_path / "disposable.sqlite3"

    settings = ServerSettings.from_environment(
        {DATABASE_PATH_VARIABLE: str(expected)}
    )

    assert settings.database_path == expected


def test_log_level_defaults_to_info(tmp_path: Path) -> None:
    settings = ServerSettings.from_environment(
        disposable_environment(tmp_path)
    )

    assert settings.log_level == "INFO"


def test_explicit_log_level_is_used(tmp_path: Path) -> None:
    environment = disposable_environment(tmp_path)
    environment[LOG_LEVEL_VARIABLE] = "DEBUG"

    settings = ServerSettings.from_environment(environment)

    assert settings.log_level == "DEBUG"


def test_log_level_resolves_to_the_canonical_name(tmp_path: Path) -> None:
    environment = disposable_environment(tmp_path)
    environment[LOG_LEVEL_VARIABLE] = "debug"

    settings = ServerSettings.from_environment(environment)

    assert settings.log_level == "DEBUG"


def test_invalid_log_level_is_rejected(tmp_path: Path) -> None:
    environment = disposable_environment(tmp_path)
    environment[LOG_LEVEL_VARIABLE] = "VERBOSE"

    with pytest.raises(SettingsError) as failure:
        ServerSettings.from_environment(environment)

    assert LOG_LEVEL_VARIABLE in str(failure.value)


def test_busy_timeout_defaults_to_five_thousand(tmp_path: Path) -> None:
    settings = ServerSettings.from_environment(
        disposable_environment(tmp_path)
    )

    assert settings.db_busy_timeout_ms == 5000


def test_explicit_busy_timeout_is_used(tmp_path: Path) -> None:
    environment = disposable_environment(tmp_path)
    environment[DB_BUSY_TIMEOUT_VARIABLE] = "1000"

    settings = ServerSettings.from_environment(environment)

    assert settings.db_busy_timeout_ms == 1000


def test_non_numeric_busy_timeout_is_rejected(tmp_path: Path) -> None:
    environment = disposable_environment(tmp_path)
    environment[DB_BUSY_TIMEOUT_VARIABLE] = "soon"

    with pytest.raises(SettingsError) as failure:
        ServerSettings.from_environment(environment)

    assert DB_BUSY_TIMEOUT_VARIABLE in str(failure.value)


def test_negative_busy_timeout_is_rejected(tmp_path: Path) -> None:
    environment = disposable_environment(tmp_path)
    environment[DB_BUSY_TIMEOUT_VARIABLE] = "-250"

    with pytest.raises(SettingsError) as failure:
        ServerSettings.from_environment(environment)

    assert DB_BUSY_TIMEOUT_VARIABLE in str(failure.value)


def test_zero_busy_timeout_is_rejected(tmp_path: Path) -> None:
    environment = disposable_environment(tmp_path)
    environment[DB_BUSY_TIMEOUT_VARIABLE] = "0"

    with pytest.raises(SettingsError) as failure:
        ServerSettings.from_environment(environment)

    assert DB_BUSY_TIMEOUT_VARIABLE in str(failure.value)


def test_process_environment_is_read_without_an_argument(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    expected = tmp_path / "disposable.sqlite3"
    monkeypatch.setenv(DATABASE_PATH_VARIABLE, str(expected))
    monkeypatch.delenv(LOG_LEVEL_VARIABLE, raising=False)
    monkeypatch.delenv(DB_BUSY_TIMEOUT_VARIABLE, raising=False)

    settings = ServerSettings.from_environment()

    assert settings.database_path == expected
    assert settings.log_level == "INFO"
    assert settings.db_busy_timeout_ms == 5000

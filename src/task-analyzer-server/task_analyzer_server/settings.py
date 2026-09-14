"""Validated runtime settings for the Task Analyzer server.

Covers PCE-44 and PCE-45 (REQ-003). Every runtime value is supplied
explicitly through the environment. There is no implicit fallback to a
development or production database, so a misconfigured process fails
visibly instead of opening the wrong file.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

DATABASE_PATH_VARIABLE = "TASK_ANALYZER_DATABASE_PATH"
LOG_LEVEL_VARIABLE = "TASK_ANALYZER_LOG_LEVEL"
DB_BUSY_TIMEOUT_VARIABLE = "TASK_ANALYZER_DB_BUSY_TIMEOUT_MS"

DEFAULT_LOG_LEVEL = "INFO"
DEFAULT_DB_BUSY_TIMEOUT_MS = 5000

SUPPORTED_LOG_LEVELS = frozenset(
    {"CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG"}
)


class SettingsError(ValueError):
    """Raised when a runtime environment value is missing or invalid.

    The message always names the environment variable at fault so an
    operator can correct the deployment without reading the source.
    """


@dataclass(frozen=True, slots=True)
class ServerSettings:
    """Runtime configuration of one server process.

    Attributes:
        database_path: Absolute path of the SQLite database file. The
            server never derives this value and never defaults it.
        log_level: Canonical standard-library logging level name.
        db_busy_timeout_ms: Bounded wait, in milliseconds, for a busy
            SQLite lock.
    """

    database_path: Path
    log_level: str
    db_busy_timeout_ms: int

    @classmethod
    def from_environment(
        cls, environment: Mapping[str, str] | None = None
    ) -> ServerSettings:
        """Build settings from environment values.

        Args:
            environment: Mapping to read the values from. Defaults to the
                process environment, which is what the runtime factory
                uses. Tests pass their own mapping so no test can reach
                a configured runtime database.

        Returns:
            The validated settings.

        Raises:
            SettingsError: If a required value is missing or any supplied
                value is invalid.
        """
        source: Mapping[str, str] = (
            os.environ if environment is None else environment
        )
        return cls(
            database_path=_read_database_path(source),
            log_level=_read_log_level(source),
            db_busy_timeout_ms=_read_busy_timeout_ms(source),
        )


def _read_database_path(environment: Mapping[str, str]) -> Path:
    """Read and validate the required database path.

    Args:
        environment: Mapping holding the runtime environment values.

    Returns:
        The configured absolute path, unresolved.

    Raises:
        SettingsError: If the value is absent, blank, or not absolute.
    """
    raw = environment.get(DATABASE_PATH_VARIABLE, "")
    candidate = raw.strip()
    if not candidate:
        raise SettingsError(
            f"{DATABASE_PATH_VARIABLE} is required and has no default:"
            " set it to the absolute path of the server database file."
        )
    path = Path(candidate)
    if not path.is_absolute():
        raise SettingsError(
            f"{DATABASE_PATH_VARIABLE} must be an absolute path; got {raw!r}."
        )
    return path


def _read_log_level(environment: Mapping[str, str]) -> str:
    """Read and validate the logging level.

    Args:
        environment: Mapping holding the runtime environment values.

    Returns:
        The canonical upper-case level name, or ``INFO`` when the
        variable is not set at all.

    Raises:
        SettingsError: If the value is not a standard level name.
    """
    raw = environment.get(LOG_LEVEL_VARIABLE)
    if raw is None:
        return DEFAULT_LOG_LEVEL
    level = raw.strip().upper()
    if level not in SUPPORTED_LOG_LEVELS:
        supported = ", ".join(sorted(SUPPORTED_LOG_LEVELS))
        raise SettingsError(
            f"{LOG_LEVEL_VARIABLE} must be one of {supported}; got {raw!r}."
        )
    return level


def _read_busy_timeout_ms(environment: Mapping[str, str]) -> int:
    """Read and validate the SQLite busy timeout.

    Args:
        environment: Mapping holding the runtime environment values.

    Returns:
        The configured timeout in milliseconds, or ``5000`` when the
        variable is not set at all.

    Raises:
        SettingsError: If the value is not a whole number above zero.
    """
    raw = environment.get(DB_BUSY_TIMEOUT_VARIABLE)
    if raw is None:
        return DEFAULT_DB_BUSY_TIMEOUT_MS
    candidate = raw.strip()
    if not _is_positive_whole_number(candidate):
        raise SettingsError(
            f"{DB_BUSY_TIMEOUT_VARIABLE} must be a whole number of"
            f" milliseconds above zero; got {raw!r}."
        )
    return int(candidate)


def _is_positive_whole_number(value: str) -> bool:
    """Report whether the text is an ASCII decimal number above zero.

    Args:
        value: Candidate text.

    Returns:
        True when the text consists only of ASCII digits and denotes a
        value greater than zero.
    """
    if not (value.isascii() and value.isdigit()):
        return False
    return int(value) > 0

"""Shared fixtures never use a configured runtime database."""

from pathlib import Path

import pytest

from task_analyzer_server import schema
from task_analyzer_server.settings import ServerSettings


@pytest.fixture
def database_path(tmp_path: Path) -> Path:
    path = tmp_path / "disposable.sqlite3"
    schema.initialize_database(path)
    return path


@pytest.fixture
def settings(database_path: Path) -> ServerSettings:
    return ServerSettings(database_path, "INFO", 5000)

"""Shared test setup; clocks are explicit and databases are disposable.
"""

from datetime import datetime
from pathlib import Path

from task_analyzer_server import schema, services
from task_analyzer_server.clock import Clock
from task_analyzer_server.settings import ServerSettings


class FixedClock:
    def __init__(self, instant: datetime) -> None:
        self.instant = instant

    def now(self) -> datetime:
        return self.instant


def configured_settings(path: Path, clock: Clock, zone: str) -> ServerSettings:
    database = path / "disposable.sqlite3"
    schema.initialize_database(database)
    settings = ServerSettings(database, "INFO", 5000)
    services.configure_zone(settings, clock, zone)
    return settings

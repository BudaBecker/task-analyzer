"""Integration tests for the explicit database initializer.

Covers PCE-34, PCE-35, PCE-45; REQ-003, REQ-010, REQ-028.

Every test targets a newly allocated temporary path. No test reads
``TASK_ANALYZER_DATABASE_PATH`` or touches any configured runtime
database.
"""

import ast
import re
import sqlite3
from contextlib import closing
from importlib import resources
from pathlib import Path

import pytest

from task_analyzer_server import schema

EXPECTED_TABLES = [
    "operation_results",
    "product_configuration",
    "schema_version",
    "tasks",
]


def package_module_sources() -> dict[str, str]:
    """Read the source of every top-level module in the package.

    Returns:
        A mapping of file name to source text.
    """
    package_files = resources.files(schema.PACKAGE_NAME)
    return {
        entry.name: entry.read_text(encoding="utf-8")
        for entry in package_files.iterdir()
        if entry.name.endswith(".py")
    }


def read_table_names(path: Path) -> list[str]:
    """List the non-internal table names of a database.

    Args:
        path: Database file to inspect.

    Returns:
        The table names, sorted.
    """
    with closing(sqlite3.connect(path)) as connection:
        rows = connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
            " AND name NOT LIKE 'sqlite_%'"
        ).fetchall()
    return sorted(row[0] for row in rows)


def test_initialization_creates_the_designed_schema(
    tmp_path: Path,
) -> None:
    """An absent file becomes a database holding the designed tables."""
    path = tmp_path / "disposable.sqlite3"

    schema.initialize_database(path)

    assert read_table_names(path) == EXPECTED_TABLES


def test_initialization_records_the_schema_version(
    tmp_path: Path,
) -> None:
    """The installed schema version is recorded by the same call."""
    path = tmp_path / "disposable.sqlite3"

    schema.initialize_database(path)

    with closing(sqlite3.connect(path)) as connection:
        rows = connection.execute(
            "SELECT schema_version_id, version FROM schema_version"
        ).fetchall()
    assert rows == [(1, 1)]


def test_a_failed_initialization_leaves_no_database_behind(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A script failure yields no database, not a partial one."""
    path = tmp_path / "disposable.sqlite3"
    monkeypatch.setattr(
        schema,
        "read_initial_schema",
        lambda: "CREATE TABLE early (a TEXT);\nNOT VALID SQL;",
    )

    with pytest.raises(sqlite3.OperationalError):
        schema.initialize_database(path)

    assert not path.exists()


def test_an_existing_database_is_not_recreated_or_overwritten(
    tmp_path: Path,
) -> None:
    """A second call fails by name and preserves the stored data."""
    path = tmp_path / "disposable.sqlite3"
    schema.initialize_database(path)
    with closing(sqlite3.connect(path)) as connection:
        connection.execute(
            "INSERT INTO product_configuration"
            " (configuration_id, product_time_zone) VALUES (1, ?)",
            ("America/Sao_Paulo",),
        )
        connection.commit()

    with pytest.raises(
        schema.DatabaseAlreadyExistsError, match=re.escape(str(path))
    ):
        schema.initialize_database(path)

    with closing(sqlite3.connect(path)) as connection:
        stored = connection.execute(
            "SELECT product_time_zone FROM product_configuration"
        ).fetchall()
    assert stored == [("America/Sao_Paulo",)]


def test_an_existing_file_is_not_overwritten(tmp_path: Path) -> None:
    """Any existing file blocks initialization and stays untouched."""
    path = tmp_path / "disposable.sqlite3"
    path.write_text("not a database", encoding="utf-8")

    with pytest.raises(
        schema.DatabaseAlreadyExistsError, match=re.escape(str(path))
    ):
        schema.initialize_database(path)

    assert path.read_text(encoding="utf-8") == "not a database"


def test_the_schema_is_read_independently_of_the_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Initialization works from an unrelated working directory."""
    working_directory = tmp_path / "elsewhere"
    working_directory.mkdir()
    monkeypatch.chdir(working_directory)
    path = tmp_path / "disposable.sqlite3"

    schema.initialize_database(path)

    assert read_table_names(path) == EXPECTED_TABLES


def test_no_other_module_invokes_the_initializer() -> None:
    """Nothing else in the package creates a database on its own."""
    callers = sorted(
        name
        for name, source in package_module_sources().items()
        if name != "schema.py" and "initialize_database" in source
    )

    assert callers == []


def test_the_initializer_imports_no_package_module() -> None:
    """The initialization transaction uses standard sqlite3 directly."""
    tree = ast.parse(package_module_sources()["schema.py"])
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imported.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            if node.level > 0:
                imported.add(".")
            elif node.module is not None:
                imported.add(node.module.split(".")[0])

    assert "sqlite3" in imported
    assert schema.PACKAGE_NAME not in imported
    assert "." not in imported

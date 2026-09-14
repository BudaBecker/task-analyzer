"""Integration tests for the SQLite connection and transaction policy.

Covers PCE-37, PCE-43; REQ-010, REQ-031.

Every test opens a newly allocated temporary database file created by
the explicit initializer. No test reads
``TASK_ANALYZER_DATABASE_PATH`` or touches any configured runtime
database.
"""

import ast
import sqlite3
import threading
import time
from importlib import resources
from pathlib import Path

import pytest

from task_analyzer_server import schema, storage

BUSY_TIMEOUT_MS = 5000
SHORT_TIMEOUT_MS = 250

INSERT_CONFIGURATION = (
    "INSERT INTO product_configuration"
    " (configuration_id, product_time_zone) VALUES (1, ?)"
)
READ_CONFIGURATION = "SELECT product_time_zone FROM product_configuration"

PRODUCT_ZONE = "America/Sao_Paulo"


@pytest.fixture
def database_path(tmp_path: Path) -> Path:
    """Create a disposable initialized database file.

    Args:
        tmp_path: pytest-allocated temporary directory.

    Returns:
        Absolute path of the newly created database file.
    """
    path = tmp_path / "disposable.sqlite3"
    schema.initialize_database(path)
    return path


def read_pragma(connection: sqlite3.Connection, name: str) -> object:
    """Read one pragma value from an open connection.

    Args:
        connection: Open connection to the disposable database.
        name: Pragma name.

    Returns:
        The reported value, or ``None`` when the pragma reports nothing.
    """
    row = connection.execute(f"PRAGMA {name}").fetchone()
    return None if row is None else row[0]


def read_configuration(path: Path) -> list[tuple[str]]:
    """Read the configuration rows through a separate connection.

    Args:
        path: Database file to read.

    Returns:
        Every stored configuration row.
    """
    with storage.open_connection(path, BUSY_TIMEOUT_MS) as connection:
        rows = connection.execute(READ_CONFIGURATION).fetchall()
    return [(row[0],) for row in rows]


def storage_source() -> str:
    """Read the source of the storage module.

    Returns:
        The text of ``storage.py`` as it is packaged.
    """
    package_files = resources.files(schema.PACKAGE_NAME)
    return package_files.joinpath("storage.py").read_text(encoding="utf-8")


def opens_a_connection(node: ast.AST) -> bool:
    """Report whether a syntax node calls ``sqlite3.connect``.

    Args:
        node: Any node of the parsed module.

    Returns:
        True when the node opens a SQLite connection.
    """
    return (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "connect"
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "sqlite3"
    )


def test_the_journal_mode_is_delete(database_path: Path) -> None:
    """The rollback journal stays on the approved delete mode."""
    with storage.open_connection(database_path, BUSY_TIMEOUT_MS) as connection:
        assert read_pragma(connection, "journal_mode") == "delete"


def test_synchronous_durability_is_extra(database_path: Path) -> None:
    """Synchronization stays at the approved EXTRA level."""
    with storage.open_connection(database_path, BUSY_TIMEOUT_MS) as connection:
        assert read_pragma(connection, "synchronous") == 3


def test_foreign_key_enforcement_is_on(database_path: Path) -> None:
    """Foreign key enforcement is enabled on every connection."""
    with storage.open_connection(database_path, BUSY_TIMEOUT_MS) as connection:
        assert read_pragma(connection, "foreign_keys") == 1


def test_the_configured_busy_timeout_is_applied(
    database_path: Path,
) -> None:
    """The bounded lock wait is the configured number of milliseconds."""
    with storage.open_connection(
        database_path, SHORT_TIMEOUT_MS
    ) as connection:
        assert read_pragma(connection, "busy_timeout") == SHORT_TIMEOUT_MS


def test_an_ignored_pragma_fails_loudly(
    database_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A misspelled pragma is refused instead of weakening durability."""
    monkeypatch.setattr(
        storage,
        "DURABILITY_PRAGMAS",
        (("jurnal_mode", "DELETE", "delete"),),
    )

    with pytest.raises(storage.DurabilityPolicyError, match="jurnal_mode"):
        with storage.open_connection(database_path, BUSY_TIMEOUT_MS):
            pass


def test_a_pragma_reporting_another_value_fails_loudly(
    database_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A pragma that takes another value is refused, naming both."""
    monkeypatch.setattr(
        storage,
        "DURABILITY_PRAGMAS",
        (("synchronous", "NORMAL", 3),),
    )

    with pytest.raises(storage.DurabilityPolicyError, match="synchronous"):
        with storage.open_connection(database_path, BUSY_TIMEOUT_MS):
            pass


def test_the_thread_check_stays_enabled(database_path: Path) -> None:
    """A connection refuses use from a thread that did not open it."""
    failures: list[sqlite3.ProgrammingError] = []

    with storage.open_connection(database_path, BUSY_TIMEOUT_MS) as connection:

        def use_from_another_thread() -> None:
            """Attempt to use the connection from a second thread."""
            try:
                connection.execute("SELECT 1")
            except sqlite3.ProgrammingError as refusal:
                failures.append(refusal)

        thread = threading.Thread(target=use_from_another_thread)
        thread.start()
        thread.join()

    assert len(failures) == 1


def test_a_missing_database_is_never_created(tmp_path: Path) -> None:
    """Opening an absent path fails and leaves no database behind."""
    path = tmp_path / "absent.sqlite3"

    with pytest.raises(sqlite3.OperationalError):
        with storage.open_connection(path, BUSY_TIMEOUT_MS):
            pass

    assert not path.exists()


def test_a_relative_path_is_refused() -> None:
    """A path that depends on the working directory is refused."""
    with pytest.raises(ValueError, match="absolute"):
        with storage.open_connection(
            Path("disposable.sqlite3"), BUSY_TIMEOUT_MS
        ):
            pass


def test_the_connection_opens_no_transaction_of_its_own(
    database_path: Path,
) -> None:
    """A statement outside an explicit transaction opens none."""
    with storage.open_connection(database_path, BUSY_TIMEOUT_MS) as connection:
        assert connection.isolation_level is None

        connection.execute(INSERT_CONFIGURATION, (PRODUCT_ZONE,))

        assert connection.in_transaction is False


def test_a_write_transaction_commits_and_is_readable_afterwards(
    database_path: Path,
) -> None:
    """Committed work is visible to a later separate connection."""
    with storage.open_connection(database_path, BUSY_TIMEOUT_MS) as connection:
        with storage.write_transaction(connection):
            connection.execute(INSERT_CONFIGURATION, (PRODUCT_ZONE,))

    assert read_configuration(database_path) == [(PRODUCT_ZONE,)]


def test_an_error_inside_a_write_transaction_rolls_back(
    database_path: Path,
) -> None:
    """An injected failure leaves no part of the write behind."""
    with storage.open_connection(database_path, BUSY_TIMEOUT_MS) as connection:
        with pytest.raises(RuntimeError, match="injected"):
            with storage.write_transaction(connection):
                connection.execute(INSERT_CONFIGURATION, (PRODUCT_ZONE,))
                raise RuntimeError("injected storage failure")

        assert connection.in_transaction is False

    assert read_configuration(database_path) == []


def test_a_failed_commit_is_not_reported_as_persisted(
    database_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A commit that fails propagates and persists nothing."""
    monkeypatch.setattr(storage, "COMMIT", "COMMIT NOT A STATEMENT")

    with storage.open_connection(database_path, BUSY_TIMEOUT_MS) as connection:
        with pytest.raises(sqlite3.OperationalError):
            with storage.write_transaction(connection):
                connection.execute(INSERT_CONFIGURATION, (PRODUCT_ZONE,))

        assert connection.in_transaction is False

    assert read_configuration(database_path) == []


def test_the_lock_wait_is_bounded_against_a_competing_writer(
    database_path: Path,
) -> None:
    """A blocked writer waits the configured time, then gives up."""
    with storage.open_connection(database_path, BUSY_TIMEOUT_MS) as holder:
        with storage.write_transaction(holder):
            with storage.open_connection(
                database_path, SHORT_TIMEOUT_MS
            ) as blocked:
                started = time.monotonic()
                with pytest.raises(sqlite3.OperationalError):
                    blocked.execute(storage.BEGIN_IMMEDIATE)
                waited = time.monotonic() - started

    assert waited >= SHORT_TIMEOUT_MS / 1000 * 0.6
    assert waited < 5.0


def test_the_connection_is_closed_when_the_call_ends(
    database_path: Path,
) -> None:
    """No connection outlives the call that opened it."""
    with storage.open_connection(database_path, BUSY_TIMEOUT_MS) as connection:
        connection.execute("SELECT 1")

    with pytest.raises(sqlite3.ProgrammingError):
        connection.execute("SELECT 1")


def test_an_open_transaction_never_outlives_the_connection(
    database_path: Path,
) -> None:
    """Leaving the call rolls back work left inside a transaction."""
    with storage.open_connection(database_path, BUSY_TIMEOUT_MS) as connection:
        connection.execute(storage.BEGIN_IMMEDIATE)
        connection.execute(INSERT_CONFIGURATION, (PRODUCT_ZONE,))

    assert read_configuration(database_path) == []


def test_storage_holds_no_shared_connection() -> None:
    """Nothing in the module keeps a connection at module level."""
    tree = ast.parse(storage_source())
    module_level_names = sorted(
        target.id
        for node in tree.body
        if isinstance(node, ast.Assign)
        for target in node.targets
        if isinstance(target, ast.Name)
    )
    opening_functions = sorted(
        function.name
        for function in ast.walk(tree)
        if isinstance(function, ast.FunctionDef)
        and any(opens_a_connection(call) for call in ast.walk(function))
    )

    assert opening_functions == ["_open"]
    assert [name for name in module_level_names if not name.isupper()] == []


def test_no_operation_transaction_uses_executescript() -> None:
    """The module never runs a script that would force a commit."""
    tree = ast.parse(storage_source())
    called = sorted(
        node.func.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "executescript"
    )

    assert called == []

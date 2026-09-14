"""Integration tests for the installed server distribution.

Covers PCE-34, PCE-35, PCE-44, PCE-45; REQ-003, REQ-010, REQ-028.
"""

import json
import os
import socket
import subprocess
import sys
import time
from collections.abc import Iterator
from contextlib import closing, contextmanager
from pathlib import Path
from uuid import uuid4

import httpx
import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]

RUNTIME_ENTRY = "task_analyzer_server.app:application_factory"
HOST = "127.0.0.1"

DATABASE_PATH_VARIABLE = "TASK_ANALYZER_DATABASE_PATH"

READINESS_TIMEOUT_SECONDS = 60.0
POLL_INTERVAL_SECONDS = 0.1
REQUEST_TIMEOUT_SECONDS = 10.0
STOP_TIMEOUT_SECONDS = 30.0
FAILURE_TIMEOUT_SECONDS = 120.0

CONFIGURATION_ROUTE = "/v1/configuration"
TASKS_ROUTE = "/v1/tasks"

PRODUCT_ZONE = "America/Sao_Paulo"
TASK_TITLE = "Read notes"

EXPECTED_SCHEMA_VERSION = "1"
EXPECTED_TABLES = "4"

PACKAGED_SCHEMA_CODE = (
    "from importlib import resources\n"
    "schema = resources.files('task_analyzer_server')"
    ".joinpath('schema/001_initial.sql').read_text(encoding='utf-8')\n"
    "print(schema.count('CREATE TABLE'))\n"
)
INSTALLED_LOCATION_CODE = (
    "import task_analyzer_server\nprint(task_analyzer_server.__file__)\n"
)
INITIALIZE_CODE = (
    "import sqlite3\n"
    "import sys\n"
    "from pathlib import Path\n"
    "from task_analyzer_server.schema import initialize_database\n"
    "target = Path(sys.argv[1])\n"
    "initialize_database(target)\n"
    "connection = sqlite3.connect(target)\n"
    "print(connection.execute("
    "'SELECT version FROM schema_version WHERE schema_version_id = 1'"
    ").fetchone()[0])\n"
    "connection.close()\n"
)


@pytest.fixture(scope="session")
def packaged_sources(tmp_path_factory: pytest.TempPathFactory) -> Path:
    destination = tmp_path_factory.mktemp("packaged-sources")
    copied = destination / "project"
    copied.mkdir()
    (copied / "pyproject.toml").write_bytes(
        (REPOSITORY_ROOT / "pyproject.toml").read_bytes()
    )
    _copy_tree(REPOSITORY_ROOT / "src", copied / "src")
    return copied


@pytest.fixture(scope="session")
def built_wheel(
    packaged_sources: Path, tmp_path_factory: pytest.TempPathFactory
) -> Path:
    output = tmp_path_factory.mktemp("built-wheel")
    _run(
        [
            sys.executable,
            "-m",
            "build",
            "--no-isolation",
            "--wheel",
            "--outdir",
            str(output),
        ],
        cwd=packaged_sources,
    )
    wheels = sorted(output.glob("*.whl"))
    assert len(wheels) == 1
    return wheels[0]


@pytest.fixture(scope="session")
def installed_python(
    built_wheel: Path, tmp_path_factory: pytest.TempPathFactory
) -> Path:
    home = tmp_path_factory.mktemp("installed-environment")
    environment = home / "runtime"
    _run(["uv", "venv", "--python", sys.executable, str(environment)])
    runtime_lock = home / "requirements.txt"
    _run(
        [
            "uv",
            "export",
            "--locked",
            "--no-dev",
            "--no-emit-project",
            "--format",
            "requirements-txt",
            "--output-file",
            str(runtime_lock),
        ],
        cwd=REPOSITORY_ROOT,
    )
    python = _environment_python(environment)
    _run(
        [
            "uv",
            "pip",
            "install",
            "--python",
            str(python),
            "--require-hashes",
            "-r",
            str(runtime_lock),
        ]
    )
    _run(
        [
            "uv",
            "pip",
            "install",
            "--python",
            str(python),
            "--no-deps",
            str(built_wheel),
        ]
    )
    return python


def _copy_tree(source: Path, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    for entry in source.iterdir():
        if entry.name in {
            "__pycache__",
            "build",
            "dist",
        } or entry.name.endswith(".egg-info"):
            continue
        if entry.is_dir():
            _copy_tree(entry, destination / entry.name)
        else:
            (destination / entry.name).write_bytes(entry.read_bytes())


def _environment_python(environment: Path) -> Path:
    windows = environment / "Scripts" / "python.exe"
    return windows if windows.exists() else environment / "bin" / "python"


def _clean_environment() -> dict[str, str]:
    inherited = {
        name: value
        for name, value in os.environ.items()
        if name not in {"PYTHONPATH", "VIRTUAL_ENV", DATABASE_PATH_VARIABLE}
    }
    inherited["PYTHONNOUSERSITE"] = "1"
    return inherited


def _run(
    command: list[str], cwd: Path | None = None
) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(
        command,
        cwd=None if cwd is None else str(cwd),
        env=_clean_environment(),
        capture_output=True,
        text=True,
        timeout=FAILURE_TIMEOUT_SECONDS,
        check=False,
    )
    assert completed.returncode == 0, (
        f"{command[1:]} failed with {completed.returncode}:"
        f" {completed.stdout}{completed.stderr}"
    )
    return completed


def _run_installed(
    python: Path, code: str, workspace: Path, *arguments: str
) -> str:
    completed = _run([str(python), "-c", code, *arguments], cwd=workspace)
    return completed.stdout.strip()


def _free_port() -> int:
    with closing(socket.socket()) as probe:
        probe.bind((HOST, 0))
        return int(probe.getsockname()[1])


@contextmanager
def running_server(
    python: Path, database: Path, workspace: Path
) -> Iterator[str]:
    port = _free_port()
    log = workspace / f"server-{port}.log"
    environment = _clean_environment()
    environment[DATABASE_PATH_VARIABLE] = str(database)
    with log.open("wb") as sink:
        process = subprocess.Popen(
            [
                str(python),
                "-m",
                "uvicorn",
                RUNTIME_ENTRY,
                "--factory",
                "--host",
                HOST,
                "--port",
                str(port),
            ],
            cwd=str(workspace),
            env=environment,
            stdout=sink,
            stderr=subprocess.STDOUT,
        )
        try:
            base_url = f"http://{HOST}:{port}"
            _await_readiness(process, base_url, log)
            yield base_url
        finally:
            _stop(process)


def _await_readiness(
    process: "subprocess.Popen[bytes]", base_url: str, log: Path
) -> None:
    deadline = time.monotonic() + READINESS_TIMEOUT_SECONDS
    with httpx.Client(timeout=REQUEST_TIMEOUT_SECONDS) as client:
        while time.monotonic() < deadline:
            if process.poll() is not None:
                raise AssertionError(
                    f"The server exited with {process.returncode} before"
                    f" it was ready: {_read(log)}"
                )
            try:
                client.get(f"{base_url}{CONFIGURATION_ROUTE}")
            except httpx.HTTPError:
                time.sleep(POLL_INTERVAL_SECONDS)
            else:
                return
    raise AssertionError(
        f"The server was not ready within {READINESS_TIMEOUT_SECONDS}"
        f" seconds: {_read(log)}"
    )


def _stop(process: "subprocess.Popen[bytes]") -> None:
    if process.poll() is None:
        process.terminate()
    try:
        process.wait(timeout=STOP_TIMEOUT_SECONDS)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=STOP_TIMEOUT_SECONDS)


def _read(log: Path) -> str:
    return log.read_text(encoding="utf-8", errors="replace")


def initialized_database(python: Path, workspace: Path) -> Path:
    target = workspace / "disposable.sqlite3"
    version = _run_installed(python, INITIALIZE_CODE, workspace, str(target))
    assert version == EXPECTED_SCHEMA_VERSION
    return target


def configure(base_url: str) -> None:
    with httpx.Client(timeout=REQUEST_TIMEOUT_SECONDS) as client:
        response = client.put(
            f"{base_url}{CONFIGURATION_ROUTE}",
            json={"product_time_zone": PRODUCT_ZONE},
        )
    assert response.status_code == 200


def create_task(base_url: str, title: str) -> httpx.Response:
    with httpx.Client(timeout=REQUEST_TIMEOUT_SECONDS) as client:
        return client.post(
            f"{base_url}{TASKS_ROUTE}",
            json={"title": title},
            headers={"Operation-Id": str(uuid4())},
        )


def read(base_url: str, route: str) -> httpx.Response:
    with httpx.Client(timeout=REQUEST_TIMEOUT_SECONDS) as client:
        return client.get(f"{base_url}{route}")


def test_the_smoke_subprocesses_import_only_the_installed_package(
    installed_python: Path, tmp_path: Path
) -> None:
    location = Path(
        _run_installed(installed_python, INSTALLED_LOCATION_CODE, tmp_path)
    )

    assert installed_python.parent.parent in location.parents
    assert REPOSITORY_ROOT not in location.parents


def test_the_installed_package_carries_the_initial_schema(
    installed_python: Path, tmp_path: Path
) -> None:
    tables = _run_installed(installed_python, PACKAGED_SCHEMA_CODE, tmp_path)

    assert tables == EXPECTED_TABLES


def test_the_installed_initializer_creates_a_disposable_database(
    installed_python: Path, tmp_path: Path
) -> None:
    target = initialized_database(installed_python, tmp_path)

    assert target.exists()
    assert target.parent == tmp_path


def test_the_installed_runtime_factory_serves_an_unconfigured_database(
    installed_python: Path, tmp_path: Path
) -> None:
    database = initialized_database(installed_python, tmp_path)

    with running_server(installed_python, database, tmp_path) as base_url:
        response = read(base_url, CONFIGURATION_ROUTE)

    assert response.status_code == 200
    assert response.json()["configured"] is False


def test_the_installed_distribution_accepts_setup_and_creation(
    installed_python: Path, tmp_path: Path
) -> None:
    database = initialized_database(installed_python, tmp_path)

    with running_server(installed_python, database, tmp_path) as base_url:
        configure(base_url)
        created = create_task(base_url, TASK_TITLE)
        listed = read(base_url, TASKS_ROUTE)

    assert created.status_code == 201
    assert [item["title"] for item in listed.json()["items"]] == [TASK_TITLE]


def test_persisted_state_survives_restarting_the_installed_server(
    installed_python: Path, tmp_path: Path
) -> None:
    database = initialized_database(installed_python, tmp_path)

    with running_server(installed_python, database, tmp_path) as first:
        configure(first)
        created = create_task(first, TASK_TITLE)
    with running_server(installed_python, database, tmp_path) as second:
        configuration = read(second, CONFIGURATION_ROUTE).json()
        listed = read(second, TASKS_ROUTE).json()

    assert created.status_code == 201
    assert configuration["product_time_zone"] == PRODUCT_ZONE
    assert [item["task_id"] for item in listed["items"]] == [
        created.json()["task"]["task_id"]
    ]


def test_startup_with_an_absent_database_fails_without_creating_it(
    installed_python: Path, tmp_path: Path
) -> None:
    absent = tmp_path / "absent.sqlite3"
    environment = _clean_environment()
    environment[DATABASE_PATH_VARIABLE] = str(absent)

    completed = subprocess.run(
        [
            str(installed_python),
            "-m",
            "uvicorn",
            RUNTIME_ENTRY,
            "--factory",
            "--host",
            HOST,
            "--port",
            str(_free_port()),
        ],
        cwd=str(tmp_path),
        env=environment,
        capture_output=True,
        text=True,
        timeout=FAILURE_TIMEOUT_SECONDS,
        check=False,
    )

    assert completed.returncode != 0
    events = "\n".join(
        json.loads(line)["event"] for line in completed.stderr.splitlines()
    )
    assert "StartupVerificationError" in events
    assert str(absent) in events
    assert not absent.exists()

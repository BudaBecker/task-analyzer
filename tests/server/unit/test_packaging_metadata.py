"""Unit tests for the declared runtime baseline.

Covers PCE-44; REQ-003.
"""

import pathlib
import tomllib

PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[3]
PYPROJECT_PATH = PROJECT_ROOT / "pyproject.toml"

APPROVED_FLOOR = (3, 13)
SUPERSEDED_FLOOR = (3, 11)


def declared_floor() -> tuple[int, int]:
    metadata = tomllib.loads(PYPROJECT_PATH.read_text(encoding="utf-8"))
    specifier = metadata["project"]["requires-python"]

    assert specifier.startswith(">="), specifier
    major, minor = specifier.removeprefix(">=").strip().split(".")[:2]
    return (int(major), int(minor))


def test_the_declared_floor_is_the_approved_minimum() -> None:
    assert declared_floor() == APPROVED_FLOOR


def test_the_declared_floor_excludes_the_preceding_version() -> None:
    assert (3, 12) < declared_floor()


def test_the_declared_floor_excludes_the_superseded_minimum() -> None:
    assert SUPERSEDED_FLOOR < declared_floor()


def test_the_declared_floor_admits_the_approved_minimum() -> None:
    assert not APPROVED_FLOOR < declared_floor()


def test_the_baseline_is_written_as_the_approved_specifier() -> None:
    metadata = tomllib.loads(PYPROJECT_PATH.read_text(encoding="utf-8"))

    assert metadata["project"]["requires-python"] == ">=3.13"

"""Unit tests for the declared runtime baseline.

Covers PCE-44; REQ-003.

The user raised the server's Python minimum from 3.11 to 3.13 on
2026-09-13. That decision lives in packaging metadata rather than in
code, so no other test fails if the floor is lowered. These tests pin it
directly: they fail if the declared baseline ever admits an interpreter
older than 3.13.

The specifier is parsed with the standard library only. ``packaging`` is
present in the locked environment as a transitive dependency, not a
declared one, so the suite does not depend on it.
"""

import pathlib
import tomllib

PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[3]
PYPROJECT_PATH = PROJECT_ROOT / "pyproject.toml"

APPROVED_FLOOR = (3, 13)
SUPERSEDED_FLOOR = (3, 11)


def declared_floor() -> tuple[int, int]:
    """Return the minimum Python version the server declares.

    Returns:
        The ``(major, minor)`` floor parsed from ``requires-python``.

    Raises:
        AssertionError: If the specifier is not a single ``>=`` floor,
            which is the only form the approved baseline uses.
    """
    metadata = tomllib.loads(PYPROJECT_PATH.read_text(encoding="utf-8"))
    specifier = metadata["project"]["requires-python"]

    assert specifier.startswith(">="), specifier
    major, minor = specifier.removeprefix(">=").strip().split(".")[:2]
    return (int(major), int(minor))


def test_the_declared_floor_is_the_approved_minimum() -> None:
    """The declared floor is exactly Python 3.13."""
    assert declared_floor() == APPROVED_FLOOR


def test_the_declared_floor_excludes_the_preceding_version() -> None:
    """Python 3.12 is below the declared floor."""
    assert (3, 12) < declared_floor()


def test_the_declared_floor_excludes_the_superseded_minimum() -> None:
    """The superseded 3.11 minimum is below the declared floor."""
    assert SUPERSEDED_FLOOR < declared_floor()


def test_the_declared_floor_admits_the_approved_minimum() -> None:
    """Python 3.13 is not below the declared floor."""
    assert not APPROVED_FLOOR < declared_floor()


def test_the_baseline_is_written_as_the_approved_specifier() -> None:
    """The declared specifier is exactly ``>=3.13``."""
    metadata = tomllib.loads(PYPROJECT_PATH.read_text(encoding="utf-8"))

    assert metadata["project"]["requires-python"] == ">=3.13"

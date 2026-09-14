# Server dependency inputs and locks

This directory holds the dependency inputs for the Task Analyzer server and the
hash-pinned lock files generated from them. The approved packaging and locking
tools are standard `venv`/`pip`, `setuptools`, `build`, and `pip-tools`, as
recorded in the [1A Design](../.specs/features/persistent-task-creation-editing/design.md#dependencies-and-quality-checks).

## Files

| File | Purpose |
| --- | --- |
| `server.in` | Direct runtime inputs. Identical to `[project].dependencies` in the root `pyproject.toml`. |
| `dev.in` | Development toolchain. Includes `-r server.in` plus pytest, HTTPX, Ruff, mypy, setuptools, build, and pip-tools. |
| `server-py313.txt` | Hash-pinned runtime resolution for the environment recorded below. |
| `dev-py313.txt` | Hash-pinned development resolution for the environment recorded below. |

FastAPI, Starlette, and Pydantic are resolved together in a single run. Never
upgrade one of them independently of the others: recompile both lock files from
the `.in` inputs instead.

## Locked environment

The locks in this directory were generated and hash-verified on the following
environment. They are environment-specific and claim no cross-platform
validation.

| Property | Value |
| --- | --- |
| Operating system | Windows 11 (10.0.26200), `Windows-11-10.0.26200-SP0` |
| Architecture | AMD64 (`win-amd64`) |
| Interpreter | CPython 3.13.2 (`3.13.2 (tags/v3.13.2:4f8bb39, Feb 4 2025) [MSC v.1942 64 bit (AMD64)]`) |
| Declared baseline | `requires-python = ">=3.13"` |

## Regenerating the locks

Run both commands from the repository root with a Python 3.13 interpreter that
has `pip-tools` installed:

```
python -m piptools compile --generate-hashes --allow-unsafe --output-file requirements/server-py313.txt requirements/server.in
python -m piptools compile --generate-hashes --allow-unsafe --output-file requirements/dev-py313.txt requirements/dev.in
```

`--allow-unsafe` pins `setuptools` and `pip` explicitly so `python -m build
--no-isolation` uses the locked build backend instead of resolving a different
one.

## Installing the development environment

```
python -m venv <env-dir>
<env-dir>/Scripts/python -m pip install --require-hashes -r requirements/dev-py313.txt
<env-dir>/Scripts/python -m pip check
```

On Linux the interpreter is `<env-dir>/bin/python`. `--require-hashes` is
mandatory: it is the reason the lock files carry hashes.

## Python baseline

Python 3.13 is the approved minimum, raised from 3.11 by the user on
2026-09-13. A dependency that cannot satisfy this baseline is reported as a
design-revision proposal. The minimum is never raised to accommodate a package.

## Open questions

- The Ubuntu Server 26.04.1 LTS target interpreter is **not confirmed**. That
  host is not reachable from the environment that produced these locks, so a
  target-specific lock and the same gates on that interpreter remain pending.
  Nothing here reports the Ubuntu target as verified. The deployment guide
  (T31) carries this as an explicit, separately authorized checkpoint.
- The installation paths, tailnet hostname, and authorized device identifiers
  for that host are still supplied by the user before deployment.

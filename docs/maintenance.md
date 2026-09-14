# Project simplification

Approved by the user on 2026-09-14 for a personal, educational and portfolio project. New features remain paused.

## Scope

Preserve the approved product behavior, REQ/PCE identifiers and protected test scenarios. Replace the mandatory TLC workflow with lightweight SDD, adopt uv, fix audit findings F1-F5 and remove repeated documentation and test scaffolding. No deployment or real database changes.

The original implementation and audit are preserved in Git at `8c68d6a`. Historical plans and evidence can be read there without loading them in everyday sessions.

## Steps

- [x] Simplify project instructions and document the approved process/tooling change.
- [x] Establish uv, a persistent ignored .venv and repeatable setup/build commands.
- [x] Fix initialization ownership, blocking routes, JSON number handling, read consistency and runtime logging, with regressions.
- [x] Consolidate explanatory text and shared test setup while preserving scenarios.
- [x] Refresh feature/product documentation, run full checks and report measured results.

## Verification

Run the full suite, Ruff formatting/lint, strict mypy, dependency checks, package build and installed-wheel smoke tests. Compare original test bodies/inputs during consolidation. Keep target-interpreter and Tailscale evidence pending.

## Results

The repository now uses `pyproject.toml`, `uv.lock`, `.python-version` and an ignored persistent `.venv`; the former pip-tools requirements set was removed. The five audit defects were fixed with 14 focused regressions: initialization ownership, event-loop blocking, non-finite/overflow JSON numbers, consistent list snapshots and Uvicorn JSON logs.

Active documentation fell from 17 files / 3,181 lines to 10 files / 745 lines. Python source stayed at 11 files and fell from 3,760 to 2,082 lines by removing restated contracts from docstrings; an AST comparison confirmed that this cleanup changed no executable statements. Tests fell from 29 files / 11,973 lines / 588 cases to 24 files / 7,061 lines / 393 cases. The final suite includes the 14 new audit regressions; 209 cases repeated at lower layers were retired, for a net reduction of 195 cases from the baseline. Shared clocks, settings and disposable paths now live in two small helpers.

Final local verification passed: locked sync, Ruff format/lint, strict mypy, dependency compatibility, 393 tests, source distribution and wheel build. The suite includes the installed-wheel startup/restart smoke test. Two third-party deprecation warnings remain in Starlette's current test client integration.

## Open questions

Deployment values and Windows client choices remain outside this maintenance scope.

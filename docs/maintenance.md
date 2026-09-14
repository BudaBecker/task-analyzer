# Project simplification

Approved by the user on 2026-09-14 for a personal, educational and portfolio project. New features remain paused.

## Scope

Preserve the approved product behavior, REQ/PCE identifiers and protected test scenarios. Replace the mandatory TLC workflow with lightweight SDD, adopt uv, fix audit findings F1-F5 and remove repeated documentation and test scaffolding. No deployment or real database changes.

The original implementation and audit are preserved in Git at `8c68d6a`. Historical plans and evidence can be read there without loading them in everyday sessions.

## Steps

- [x] Simplify project instructions and document the approved process/tooling change.
- [x] Establish uv, a persistent ignored .venv and repeatable setup/build commands.
- [x] Fix initialization ownership, blocking routes, JSON number handling, read consistency and runtime logging, with regressions.
- [ ] Consolidate explanatory text and shared test setup while preserving scenarios.
- [ ] Refresh feature/product documentation, run full checks and report measured results.

## Verification

Run the full suite, Ruff formatting/lint, strict mypy, dependency checks, package build and installed-wheel smoke tests. Compare original test bodies/inputs during consolidation. Keep target-interpreter and Tailscale evidence pending.

## Results

uv migration: the persistent .venv is installed and all 588 original cases pass, including installed-wheel startup/restart. Runtime and retained development dependency versions match the original locks.

Work in progress. Baseline: 11 Python source files / 3,760 lines; 29 test files / 11,973 lines; 588 executed test cases. Final measurements and checks will replace this paragraph.

## Open questions

Deployment values and Windows client choices remain outside this maintenance scope.

# LESSONS - auto-maintained by scripts/lessons.py

> Machine-owned. Do NOT hand-edit. Changes are overwritten on the next `lessons.py` write.
> Canonical state lives in `.specs/lessons.json`. Edit lessons only via the script.
> promote_threshold=2 distinct features · window_days=45 · quarantine_threshold=2

## Confirmed (load these at Specify/Design)

Corroborated across multiple features. Safe to apply as guidance.

_none_

## Candidates (under observation - do NOT load as guidance yet)

Seen once or not yet corroborated. Tracked, not trusted.

### L-001 - Pin approved configuration and packaging values with a test that fails when the value is changed, because a metadata-only decision breaks no other test when it is reversed.
- signal: `surviving_mutant` · recurrence: 1 feature(s) · scope: `packaging` · harmful: 0
- features: persistent-task-creation-editing
- evidence: validation.md Finding 2 (mutant M11); pyproject.toml:9 (packaging)
- last seen: 2026-09-14T10:25:35Z

### L-002 - Run discrimination mutations with PYTHONPATH pinned to the scratch copy and verify the module resolved there, because an editable install resolves imports back to the real checkout and every mutant falsely survives.
- signal: `surviving_mutant` · recurrence: 1 feature(s) · scope: `verification` · harmful: 0
- features: persistent-task-creation-editing
- evidence: validation.md sensor pass 1 (all 10 mutants falsely survived) (verification)
- last seen: 2026-09-14T10:25:40Z

### L-003 - Acquire exclusive ownership before initializing a database and clean up only files owned by that attempt.
- signal: `ac_gap` · recurrence: 1 feature(s) · scope: `storage` · harmful: 0
- features: persistent-task-creation-editing
- evidence: validation.md F1 (storage)
- last seen: 2026-09-14T17:13:00Z

### L-004 - Test concurrent HTTP progress under real SQLite contention to detect blocking work on the event loop.
- signal: `ac_gap` · recurrence: 1 feature(s) · scope: `api` · harmful: 0
- features: persistent-task-creation-editing
- evidence: validation.md F2 (api)
- last seen: 2026-09-14T17:13:00Z

### L-005 - Exercise JSON parser and canonicalization boundaries through HTTP and assert the exact rejection and retained outcome.
- signal: `ac_gap` · recurrence: 1 feature(s) · scope: `api` · harmful: 0
- features: persistent-task-creation-editing
- evidence: validation.md F3 (api)
- last seen: 2026-09-14T17:13:00Z

### L-006 - Read related response metadata and rows within one database snapshot and test concurrent setup.
- signal: `ac_gap` · recurrence: 1 feature(s) · scope: `storage` · harmful: 0
- features: persistent-task-creation-editing
- evidence: validation.md F4 (storage)
- last seen: 2026-09-14T17:13:00Z

### L-007 - Verify structured logging through the actual runtime logger configuration, including server and access handlers.
- signal: `ac_gap` · recurrence: 1 feature(s) · scope: `logging` · harmful: 0
- features: persistent-task-creation-editing
- evidence: validation.md F5 (logging)
- last seen: 2026-09-14T17:13:00Z

## Quarantined (failed when applied - ignore)

A confirmed lesson that recurred alongside failure. Kept for the maintainer to review.

_none_

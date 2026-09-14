# Persistent Task Creation and Editing Tasks

## Execution Protocol (MANDATORY -- do not skip)

Implement these tasks with the `tlc-spec-driven` skill: **activate it by name and follow its Execute flow and Critical Rules.** Do not search for skill files by filesystem path. The skill is the source of truth for the full flow (per-task cycle, sub-agent delegation, adequacy review, Verifier, discrimination sensor).

**If the skill cannot be activated, STOP and tell the user - do not proceed without it.**

**Commits and authorization.** This project follows TLC's commit standard, as recorded in [AGENTS.md](../../../AGENTS.md#branches-and-authorization): every task ends in one atomic Conventional Commit on the work branch, created without asking for a further approval, with that task's status and traceability updates included in the same commit. Validate each message with `check_commit.py`, never batch tasks into one commit, and never commit a task whose gate has not passed. Pushing, merging, deploying, initializing or migrating a real database, and any Tailscale host configuration remain separately authorized actions. The independent Verifier runs on the working tree, including uncommitted and untracked files.

---

**Spec**: [spec.md](spec.md)
**Design**: [design.md](design.md) (approved 2026-09-13)
**Status**: Draft - awaiting task approval

---

## Test Coverage Matrix

> Generated from project guidelines, the approved design, and the spec - confirm before Execute. Guidelines found: `AGENTS.md` (Tests and verification, server-side Python conventions, persistence safeguards), [design.md](design.md) (Dependencies and Quality Checks, Test and Requirement Coverage). No test runner configuration, no existing tests, and no application code exist yet (`src/task-analyzer-server/` and `tests/` are empty), so the matrix is derived from those approved sources rather than from codebase sampling, and T1-T2 create the tooling it names.

| Code Layer | Required Test Type | Coverage Expectation | Location Pattern | Run Command |
| --- | --- | --- | --- | --- |
| Domain rules - `domain.py`, `clock.py` | unit | All branches; 1:1 with the PCE criteria listed on the task; every approved boundary fixture (200/201, 5,000/5,001, protected title examples, September 14/15 cutoff, repeated and missing midnight) | `tests/server/unit/test_*.py` | `python -m pytest tests/server/unit` |
| Wire contracts - `contracts.py` | unit | Every public field and rejection branch: strict types, unknown fields, null clearing, exact serialization format | `tests/server/unit/test_*.py` | `python -m pytest tests/server/unit` |
| Runtime configuration - `settings.py`, `logging_config.py` | unit | Valid and invalid configuration branches, required-value failures, record formatting and forbidden-field exclusion | `tests/server/unit/test_*.py` | `python -m pytest tests/server/unit` |
| Persistence - `schema/*.sql`, `schema.py`, `storage.py` | integration | Key read/write paths plus constraint, index, transaction, and lock error paths, always against a newly allocated disposable database file | `tests/server/integration/test_*.py` | `python -m pytest tests/server/integration` |
| Operation services - `services.py` | integration | All branches; 1:1 with the PCE criteria listed on the task; replay, conflict, rejection, restart, and rollback paths | `tests/server/integration/test_*.py` | `python -m pytest tests/server/integration` |
| API - `api.py`, `app.py` | e2e | Every route the task adds: happy path, every listed edge case, and error/protocol paths, exercised through the composed application | `tests/server/integration/test_api_*.py` | `python -m pytest tests/server/integration` |
| Packaging and deployment assets - `pyproject.toml`, `requirements/`, `*.service`, deployment guide | none | build gate only | - | build gate only |

E2E tests live under `tests/server/integration/` because the approved design defines exactly two test locations; the `test_api_*` prefix keeps the route-level suites identifiable. Every test module records the REQ and PCE IDs it covers. Tests assert spec-defined outcomes, never internal calls. Every database used by a test is a newly allocated temporary file; no test may fall back to `TASK_ANALYZER_DATABASE_PATH` or any non-disposable database.

## Gate Check Commands

> Generated from the approved design's quality gates - confirm before Execute. The commands become executable once T1 and T2 install the configured environment; T2 is the first task that runs the full Build gate.

| Gate Level | When to Use | Command |
| --- | --- | --- |
| Quick | After tasks with unit tests only | `python -m pytest tests/server/unit` |
| Full | After tasks with integration or e2e tests | `python -m pytest tests/server` |
| Build | After phase completion or config/asset-only tasks | `python -m ruff format --check src/task-analyzer-server tests/server`, then `python -m ruff check src/task-analyzer-server tests/server`, then `python -m mypy --strict src/task-analyzer-server/task_analyzer_server`, then `python -m pytest tests/server`, then `python -m pip check`, then `python -m build` with an install-and-import check of the built wheel in an isolated environment |

Commands are listed separately rather than chained so they run unchanged in PowerShell and POSIX shells. Run them from the repository root in the locked development environment created by T2.

---

## Execution Plan

Phases are ordered and run sequentially - each phase completes before the next begins, and tasks within a phase execute in order.

### Phase 1: Project and runtime foundation

Tool configuration, locked dependencies, and the two standalone runtime modules.

```
T1 → T2 → T3
T2 → T4
```

### Phase 2: Database schema

The versioned DDL and its explicit initialization entry point.

```
T5 → T6
```

### Phase 3: Domain and time rules

Pure rules with no storage or transport dependency.

```
T7 → T8
T9 → T10
```

### Phase 4: Wire contracts

Strict request and response models.

```
T11 → T12
```

### Phase 5: Storage access

Connection policy, configuration singleton, task access, and the operation ledger.

```
T13 → T14
T13 → T15
T13 → T16
```

### Phase 6: Operation services

The transactional runner, configuration setup, and the two 1A commands.

```
T17 → T19 → T20 → T21
T19 → T21
T18 has no intra-phase dependency.
```

### Phase 7: API composition and routes

Application composition followed by one route group per task.

```
T22 → T23
T22 → T24
T22 → T25 → T26 → T27
```

### Phase 8: Cross-cutting scenario verification

Durability, restart, concurrency, and fault-injection suites that no single module owns.

```
T28 → T29
```

### Phase 9: Deployment assets

Proposed service asset and the deployment and private-access guide.

```
T30 → T31
```

---

## Task Breakdown

Every task carries the PCE and REQ IDs it serves, keeps its tests in the same task, and leaves persisted behaviour unchanged for rejected operations. No MCP server and no additional skill are used in this delivery - the user confirmed on 2026-09-13 that neither is needed. The `tlc-spec-driven` skill still drives the Execute flow itself, and the Knowledge Verification Chain relies on the codebase, the project documents, and the official documentation already cited in the design.

### T1: Configure the server package and tool baseline

**What**: Add the root `pyproject.toml` declaring the server package, the Python 3.13 minimum, direct runtime dependencies, and the approved Ruff, mypy, and pytest configuration.
**Where**: `pyproject.toml`
**Depends on**: None
**Reuses**: [design.md](design.md) "Dependencies and Quality Checks" (79-character Ruff limit, Google docstring convention, import ordering, mypy strict, skill bundles excluded).
**Requirement**: PCE-44; REQ-003.

**Tools**:

- MCP: NONE
- Skill: NONE

**Done when**:

- [ ] `requires-python = ">=3.13"` and package discovery resolves `src/task-analyzer-server/task_analyzer_server`.
- [ ] Direct runtime dependencies are declared: FastAPI, Uvicorn, Pydantic v2, `regex`, and `tzdata`; no exact versions are invented here - T2 resolves and pins them.
- [ ] Ruff (line length 79, Google docstrings, import ordering, error and unused-code rules), mypy strict for the server package, and pytest `testpaths = ["tests/server"]` are configured; `.ai/` skill bundles are excluded from lint and type targets.
- [ ] No client or desktop tooling is configured.
- [ ] `python -m pip install -e .` succeeds in a disposable virtual environment on Python 3.13.
- [ ] Gate check: the Build gate's tool commands are configured but not yet installable, so T2 runs them for the first time. Record that explicitly instead of claiming an unperformed run.

**Tests**: none
**Gate**: build

**Commit**: `chore(server): configure package and tool baseline`

---

### T2: Lock server and development dependencies

**What**: Add `requirements/server.in` and `requirements/dev.in` with their hash-pinned generated lock files, and install the development environment.
**Where**: `requirements/`
**Depends on**: T1
**Reuses**: T1's declared direct dependencies; the design's packaging and locking decisions (venv, pip, setuptools, build, pip-tools).
**Requirement**: PCE-44, PCE-45; REQ-003.

**Tools**:

- MCP: NONE
- Skill: NONE

**Done when**:

- [ ] `requirements/server.in` lists the runtime inputs and `requirements/dev.in` lists pytest, HTTPX, Ruff, mypy, build, and pip-tools.
- [ ] Generated lock files pin exact released versions with hashes for Python 3.13; FastAPI, Starlette, and Pydantic are resolved together and never upgraded independently.
- [ ] A dependency incompatible with the Python 3.13 baseline is reported as a design-revision proposal instead of raising the minimum.
- [ ] The design requires the lock to be compatible with the interpreter the Ubuntu target provides. That host is not accessible from this environment, so T2 locks against the declared 3.13 baseline and records the target-interpreter confirmation as an explicit pending item in the deployment guide (T31). It is never reported as performed.
- [ ] `python -m pip check` reports no broken requirements in the locked environment.
- [ ] Gate check passes: `python -m ruff format --check src/task-analyzer-server tests/server`, `python -m ruff check src/task-analyzer-server tests/server`, and `python -m mypy --strict src/task-analyzer-server/task_analyzer_server` execute cleanly on the current empty targets; `python -m pytest tests/server` reports no tests collected, the expected state before T3.

**Tests**: none
**Gate**: build

**Commit**: `chore(server): lock runtime and development dependencies`

---

### T3: Implement validated runtime settings

**What**: Add `ServerSettings` reading and validating the approved environment values with no implicit database fallback.
**Where**: `src/task-analyzer-server/task_analyzer_server/settings.py`
**Depends on**: T2
**Reuses**: The design's runtime environment values; the AGENTS.md persistence safeguards.
**Requirement**: PCE-44, PCE-45; REQ-003.

**Tools**:

- MCP: NONE
- Skill: NONE

**Done when**:

- [ ] `TASK_ANALYZER_DATABASE_PATH` is required and must be absolute; a missing or relative value raises a specific error naming the variable.
- [ ] `TASK_ANALYZER_LOG_LEVEL` defaults to `INFO` and `TASK_ANALYZER_DB_BUSY_TIMEOUT_MS` defaults to `5000`; invalid values are rejected rather than silently coerced.
- [ ] No default points at a development or production database; every test supplies its own disposable path.
- [ ] Google-style docstrings and complete type annotations are present.
- [ ] Gate check passes: `python -m pytest tests/server/unit`.
- [ ] Test count: at least 8 tests pass in `tests/server/unit/test_settings.py` (no silent deletions).

**Tests**: unit
**Gate**: quick

**Commit**: `feat(server): add validated runtime settings`

---

### T4: Implement JSON-line structured logging

**What**: Add `configure_logging(level)` producing the approved JSON-line records through the standard `logging` module.
**Where**: `src/task-analyzer-server/task_analyzer_server/logging_config.py`
**Depends on**: T2
**Reuses**: The design's logging field list; the AGENTS.md structured-logging rule.
**Requirement**: PCE-44; REQ-003.

**Tools**:

- MCP: NONE
- Skill: NONE

**Done when**:

- [ ] Records serialize as one JSON object per line with `timestamp`, `level`, `event`, `request_id`, optional `operation_id` and `task_id`, `outcome`, `error_code`, and `duration_ms`.
- [ ] Task titles, observations, request bodies, canonical requests, and secrets are never emitted, asserted by a test that supplies those values and checks their absence.
- [ ] Durations come from a monotonic clock, and a formatting failure cannot raise into caller control flow.
- [ ] Gate check passes: `python -m pytest tests/server/unit`.
- [ ] Test count: at least 6 tests pass in `tests/server/unit/test_logging_config.py` (no silent deletions).

**Tests**: unit
**Gate**: quick

**Commit**: `feat(server): add json line structured logging`

---

### T5: Add the versioned initial schema

**What**: Add the initial DDL creating `product_configuration`, `tasks`, `operation_results`, `schema_version`, and the two unique partial indexes.
**Where**: `src/task-analyzer-server/task_analyzer_server/schema/001_initial.sql`
**Depends on**: T2
**Reuses**: The design's data-model records and uniqueness index definitions.
**Requirement**: PCE-19, PCE-20, PCE-24, PCE-25, PCE-29; REQ-028, REQ-029, REQ-031.

**Tools**:

- MCP: NONE
- Skill: NONE

**Done when**:

- [ ] Tables and columns match the design exactly, including UUID text keys, `title_key`, nullable observations and `deadline_date`, integer UTC-microsecond timestamps, `status` restricted to `pending`/`completed`, and `is_deleted` restricted to `0`/`1`.
- [ ] The dated index is unique on `(title_key, deadline_date)` where `is_deleted=0 AND deadline_date IS NOT NULL`, irrespective of status; the undated index is unique on `title_key` where `is_deleted=0 AND deadline_date IS NULL AND status='pending'`.
- [ ] `operation_results` stores the canonical request text, terminal outcome, original HTTP status, serialized result, and resolution timestamp, with no cascading task foreign key.
- [ ] `schema_version` is a singleton distinct from product configuration.
- [ ] Integration tests apply the DDL to a newly allocated temporary database file and assert each constraint by attempting the violating write: duplicate dated combination rejected, duplicate undated pending title rejected, completed undated duplicate allowed, deleted rows excluded, invalid `status` and `is_deleted` rejected.
- [ ] Gate check passes: `python -m pytest tests/server`.
- [ ] Test count: at least 12 tests pass in `tests/server/integration/test_schema_sql.py` (no silent deletions).

**Tests**: integration
**Gate**: full

**Commit**: `feat(server): add versioned initial database schema`

---

### T6: Implement the explicit database initializer

**What**: Add `initialize_database(path)` as the only entry point that creates a new database from the versioned DDL.
**Where**: `src/task-analyzer-server/task_analyzer_server/schema.py`
**Depends on**: T5
**Reuses**: T5's DDL asset; the design's startup policy that the application never initializes, migrates, or recreates a database.
**Requirement**: PCE-34, PCE-35, PCE-45; REQ-003, REQ-010, REQ-028.

**Tools**:

- MCP: NONE
- Skill: NONE

**Done when**:

- [ ] Initialization creates the schema and records the schema version in one transaction against an absent file.
- [ ] An existing database is never silently recreated, migrated, or overwritten; the function raises a specific error identifying the path.
- [ ] The initializer is importable but is never invoked at application startup.
- [ ] Integration tests run only against newly allocated temporary paths; no test targets a configured runtime database.
- [ ] Gate check passes: `python -m pytest tests/server`.
- [ ] Test count: at least 6 tests pass in `tests/server/integration/test_schema_init.py` (no silent deletions).

**Tests**: integration
**Gate**: full

**Commit**: `feat(server): add explicit database initializer`

---

### T7: Implement task field validation

**What**: Add `validate_task` enforcing the approved title, observations, and deadline rules with user-perceived character counting.
**Where**: `src/task-analyzer-server/task_analyzer_server/domain.py`
**Depends on**: T2
**Reuses**: The design's text-bounds rules and stable field-error codes.
**Requirement**: PCE-01 through PCE-10, PCE-15, PCE-16, PCE-48, PCE-51, PCE-52; REQ-007, REQ-008, REQ-011.

**Tools**:

- MCP: NONE
- Skill: NONE

**Done when**:

- [ ] The title is counted in extended grapheme clusters after trimming leading and trailing spaces; an empty or whitespace-only title is rejected as `TITLE_REQUIRED` independently of the limit.
- [ ] A 200-cluster title is accepted and 201 rejected as `TITLE_TOO_LONG`; 5,000-cluster observations are accepted and 5,001 rejected as `OBSERVATIONS_TOO_LONG`; observations are counted as supplied with line breaks preserved.
- [ ] Absent observations and an absent deadline are accepted; a valid past calendar date in the supported range is accepted; a non-calendar or out-of-range date is rejected as `INVALID_DEADLINE`. Tests accept both `0001-01-01` and `9999-12-30` and reject `9999-12-31`; range checks occur before cutoff arithmetic.
- [ ] Accepted input is never truncated, and counting stops once a limit is exceeded.
- [ ] Unit tests cover each criterion with both the original simple-text fixtures and combined-character fixtures: a base letter with combining marks and a joined emoji sequence each count as one character.
- [ ] Gate check passes: `python -m pytest tests/server/unit`.
- [ ] Test count: at least 24 tests pass in `tests/server/unit/test_domain_validation.py` (no silent deletions).

**Tests**: unit
**Gate**: quick

**Commit**: `feat(server): add task field validation`

---

### T8: Implement the title comparison key

**What**: Add `title_key` deriving the uniqueness comparison key without altering submitted text.
**Where**: `src/task-analyzer-server/task_analyzer_server/domain.py` (modify)
**Depends on**: T7
**Reuses**: T7's module and the design's comparison rules.
**Requirement**: PCE-17, PCE-18, PCE-23; REQ-029.

**Tools**:

- MCP: NONE
- Skill: NONE

**Done when**:

- [ ] The key trims edge spaces, collapses runs of internal U+0020 to one space, and applies Unicode case folding while retaining accents.
- [ ] Accents are never stripped, compatibility normalization is not applied, and interior tabs or newlines are not collapsed into spaces.
- [ ] Key generation is centralized so checks and stored keys always use the identical function; submitted text is returned unchanged alongside the key.
- [ ] Unit tests preserve the protected examples: `Read notes` and the doubly spaced uppercase variant produce the same key, while `Review résumé` and `Review resume` produce different keys.
- [ ] Gate check passes: `python -m pytest tests/server/unit`.
- [ ] Test count: at least 10 tests pass in `tests/server/unit/test_domain_title_key.py` (no silent deletions).

**Tests**: unit
**Gate**: quick

**Commit**: `feat(server): add title comparison key`

---

### T9: Implement the server clock and product date

**What**: Add the `Clock` protocol and its default implementation supplying aware UTC instants, the product date, and microsecond conversions.
**Where**: `src/task-analyzer-server/task_analyzer_server/clock.py`
**Depends on**: T2
**Reuses**: The design's time-representation rules; standard `datetime` and `zoneinfo`.
**Requirement**: PCE-28, PCE-30, PCE-31; REQ-028.

**Tools**:

- MCP: NONE
- Skill: NONE

**Done when**:

- [ ] `now()` returns an aware UTC `datetime`; conversion to and from integer UTC microseconds uses integer and timedelta arithmetic, never floating-point epoch rounding.
- [ ] The product date derives from server time converted into the retained IANA product zone.
- [ ] The clock is substitutable so tests supply a controlled instant; no other service dependency needs substitution.
- [ ] Unit tests assert that a changed host display zone does not alter the product date derived from the configured zone.
- [ ] Gate check passes: `python -m pytest tests/server/unit`.
- [ ] Test count: at least 10 tests pass in `tests/server/unit/test_clock.py` (no silent deletions).

**Tests**: unit
**Gate**: quick

**Commit**: `feat(server): add server clock and product date`

---

### T10: Implement deadline cutoff resolution

**What**: Add `deadline_cutoff` converting a calendar deadline into its UTC cutoff instant, including the approved exceptional-midnight rules.
**Where**: `src/task-analyzer-server/task_analyzer_server/clock.py` (modify)
**Depends on**: T9
**Reuses**: T9's conversion helpers; the design's fold and gap resolution procedure.
**Requirement**: PCE-32, PCE-33, PCE-49, PCE-50, PCE-51, PCE-52; REQ-011.

**Tools**:

- MCP: NONE
- Skill: NONE

**Done when**:

- [ ] The cutoff is the next calendar date's local midnight in the product zone converted to UTC, never the deadline start plus 24 hours.
- [ ] A repeated midnight resolves to its first UTC occurrence; an absent midnight resolves to the first valid instant at or after the nominal next-day boundary, including after a wholly skipped date, located by bracketing the transition with integer-microsecond bisection rather than by adding an offset difference.
- [ ] Resolved instants are validated against the intended calendar boundary before being returned, including the preceding-microsecond check. Fixtures cover the supported date endpoints with UTC and positive/negative-offset zones. No overflow may become an invented cutoff or an accepted out-of-range deadline.
- [ ] A pending task whose cutoff has been reached is reported as overdue under the deadline semantics; no emphasis category and no grace period are introduced.
- [ ] Unit tests preserve the approved September 14 example: valid throughout September 14 and overdue at September 15 00:00 in the product zone. Repeated-midnight and missing-midnight fixtures use expected instants from independently checked zone-transition data, never from calling the helper under test. A `2011-12-29` deadline in `Pacific/Apia` resolves to `2011-12-30T10:00:00.000000Z`, skipping the absent December 30 local date.
- [ ] Gate check passes: `python -m pytest tests/server/unit`.
- [ ] Test count: at least 12 tests pass in `tests/server/unit/test_clock_cutoff.py` (no silent deletions).

**Tests**: unit
**Gate**: quick

**Commit**: `feat(server): add deadline cutoff resolution`

---

### T11: Implement strict request contracts

**What**: Add the task input and operation envelope request models with strict parsing and stable field-error codes.
**Where**: `src/task-analyzer-server/task_analyzer_server/contracts.py`
**Depends on**: T7
**Reuses**: T7's validation issues and codes; the design's input rules; Pydantic v2 strict mode.
**Requirement**: PCE-01, PCE-10, PCE-11, PCE-16, PCE-48; REQ-007, REQ-008.

**Tools**:

- MCP: NONE
- Skill: NONE

**Done when**:

- [ ] `TaskInput` accepts `title` string, `observations` string or null, and `deadline` calendar-date string or null; `null` clears an optional value and an omitted optional value means absent.
- [ ] Type coercion is rejected as `INVALID_FIELD_TYPE`, unknown fields as `UNEXPECTED_FIELD`, and server-owned fields such as status or creation time are rejected rather than silently applied.
- [ ] `OperationRequest` binds the operation UUID, method, canonical task target, and parsed JSON payload.
- [ ] Framework validation errors are translated into the stable codes; framework error objects and echoed input never reach the contract surface.
- [ ] Gate check passes: `python -m pytest tests/server/unit`.
- [ ] Test count: at least 16 tests pass in `tests/server/unit/test_contracts_input.py` (no silent deletions).

**Tests**: unit
**Gate**: quick

**Commit**: `feat(server): add strict request contracts`

---

### T12: Implement response and result contracts

**What**: Add the snapshot, configuration, list, operation-result, operation-error, and protocol-error response models with their exact serialization.
**Where**: `src/task-analyzer-server/task_analyzer_server/contracts.py` (modify)
**Depends on**: T11
**Reuses**: T11's module and codes; the design's response-shape table.
**Requirement**: PCE-26, PCE-38, PCE-40, PCE-41, PCE-43; REQ-010, REQ-029, REQ-031.

**Tools**:

- MCP: NONE
- Skill: NONE

**Done when**:

- [ ] `TaskSnapshot` exposes exactly `task_id`, `title`, `observations`, `deadline`, `status`, `created_at`, and `completed_at`; internal comparison and deletion fields are never exposed.
- [ ] `ConfigurationView` and the task-list response carry the configured flag or zone, `server_now`, and `product_date`, with an empty `items` array for an empty collection.
- [ ] `OperationResult` carries `operation_id`, `outcome`, `original_http_status`, nullable `task`, nullable `error`, and `resolved_at`, with exactly one of `task` and `error` non-null, asserted in both directions.
- [ ] `OperationError` carries a stable `code`, a `fields` array of field and code pairs that is empty for a non-field error, and a nullable `conflicting_task_id`; `ProtocolError` carries no terminal `outcome`.
- [ ] UTC instants serialize with an explicit `Z` suffix and six fractional digits; deadlines serialize as `YYYY-MM-DD`; UUIDs serialize as canonical lowercase hyphenated text.
- [ ] A test asserts that the design's example persisted creation result serializes field for field.
- [ ] Gate check passes: `python -m pytest tests/server/unit`.
- [ ] Test count: at least 18 tests pass in `tests/server/unit/test_contracts_results.py` (no silent deletions).

**Tests**: unit
**Gate**: quick

**Commit**: `feat(server): add response and result contracts`

---

### T13: Implement the SQLite connection and transaction policy

**What**: Add connection opening with verified PRAGMAs, the bounded lock wait, and the explicit immediate-transaction boundary.
**Where**: `src/task-analyzer-server/task_analyzer_server/storage.py`
**Depends on**: T6
**Reuses**: T6's initialized schema for tests; the design's SQLite connection and durability policy.
**Requirement**: PCE-37, PCE-43; REQ-010, REQ-031.

**Tools**:

- MCP: NONE
- Skill: NONE

**Done when**:

- [ ] Connections open an existing database file by absolute path with `journal_mode=DELETE`, `synchronous=EXTRA`, `foreign_keys=ON`, the configured busy timeout, and Python's thread check enabled.
- [ ] Effective PRAGMA values are read back and a mismatch fails loudly, so a misspelled or ignored PRAGMA can never silently weaken durability.
- [ ] Transactions use explicit `BEGIN IMMEDIATE` with `isolation_level=None`, and `executescript()` is never used inside an operation transaction.
- [ ] Each connection is opened, used, and closed within the same synchronous call; no shared global connection exists and no transaction spans response streaming.
- [ ] An unexpected error rolls back an active transaction and closes the connection; a failed commit is never reported as persisted.
- [ ] Integration tests assert the read-back PRAGMA values, a bounded lock wait against a competing writer, and rollback on an injected error.
- [ ] Gate check passes: `python -m pytest tests/server`.
- [ ] Test count: at least 10 tests pass in `tests/server/integration/test_storage_connection.py` (no silent deletions).

**Tests**: integration
**Gate**: full

**Commit**: `feat(server): add sqlite connection and transaction policy`

---

### T14: Implement product configuration storage

**What**: Add the singleton configuration read and the compare-and-set insert for the fixed product time zone.
**Where**: `src/task-analyzer-server/task_analyzer_server/storage.py` (modify)
**Depends on**: T13
**Reuses**: T13's connection and transaction helpers.
**Requirement**: PCE-29, PCE-35; REQ-028.

**Tools**:

- MCP: NONE
- Skill: NONE

**Done when**:

- [ ] Reading an unconfigured database returns an explicit unset result rather than a fabricated zone.
- [ ] The compare-and-set insert stores the zone only when the singleton is unset; an existing zone is never replaced, and the caller can distinguish an identical key from a different key.
- [ ] All statements are parameterized; no SQL is built by string concatenation.
- [ ] Integration tests confirm the stored zone is readable by a new connection after the transaction commits.
- [ ] Gate check passes: `python -m pytest tests/server`.
- [ ] Test count: at least 8 tests pass in `tests/server/integration/test_storage_configuration.py` (no silent deletions).

**Tests**: integration
**Gate**: full

**Commit**: `feat(server): add product configuration storage`

---

### T15: Implement task storage access

**What**: Add task insert, update, managed-task reads, and the uniqueness conflict lookup.
**Where**: `src/task-analyzer-server/task_analyzer_server/storage.py` (modify)
**Depends on**: T13, T8
**Reuses**: T13's transaction helpers and T8's centralized comparison key.
**Requirement**: PCE-11 through PCE-14, PCE-19 through PCE-25, PCE-36; REQ-008, REQ-010, REQ-029.

**Tools**:

- MCP: NONE
- Skill: NONE

**Done when**:

- [ ] Insert stores a server-generated UUID identity, submitted text, the derived `title_key`, status `pending`, `is_deleted=0`, no completion timestamp, and the supplied creation instant.
- [ ] Update replaces the editable fields and the derived key while leaving identity, creation time, and status untouched.
- [ ] Managed-task reads exclude `is_deleted=1` rows and return a committed snapshot.
- [ ] The conflict lookup implements both populations - dated `(title_key, deadline_date)` across pending and completed rows, undated `title_key` across pending rows only - excludes deleted rows, and excludes a supplied task identity from comparison.
- [ ] Integration tests cover each uniqueness population with the protected title examples, including dated versus undated coexistence, different deadline dates, self-exclusion, completed undated candidates, and deleted candidates, using fixtures for completed and deleted rows.
- [ ] Gate check passes: `python -m pytest tests/server`.
- [ ] Test count: at least 22 tests pass in `tests/server/integration/test_storage_tasks.py` (no silent deletions).

**Tests**: integration
**Gate**: full

**Commit**: `feat(server): add task storage access`

---

### T16: Implement the operation result ledger

**What**: Add the ledger read and the in-transaction write of an immutable terminal operation result.
**Where**: `src/task-analyzer-server/task_analyzer_server/storage.py` (modify)
**Depends on**: T13, T12
**Reuses**: T13's transaction helpers and T12's serialized result representation.
**Requirement**: PCE-37 through PCE-43; REQ-010, REQ-031.

**Tools**:

- MCP: NONE
- Skill: NONE

**Done when**:

- [ ] The ledger read returns the stored terminal result or an explicit unknown; unknown is never represented as a rejection.
- [ ] The write stores the operation UUID, the canonical request text itself, the terminal outcome, the original HTTP status, the immutable serialized result, and the server resolution timestamp inside the caller's open transaction.
- [ ] A stored result is never updated or deleted; retention has no TTL and no purge.
- [ ] Result rows survive independently of task rows, with no cascading task foreign key.
- [ ] Integration tests confirm that canonical-request equality is compared against the stored text, that a second write for the same operation identity does not overwrite the original, and that a committed result is readable by a new connection.
- [ ] Gate check passes: `python -m pytest tests/server`.
- [ ] Test count: at least 12 tests pass in `tests/server/integration/test_storage_operations.py` (no silent deletions).

**Tests**: integration
**Gate**: full

**Commit**: `feat(server): add operation result ledger`

---

### T17: Implement the transactional operation runner

**What**: Add the canonical request builder and the shared operation runner that resolves replays and protocol conflicts inside one transaction.
**Where**: `src/task-analyzer-server/task_analyzer_server/services.py`
**Depends on**: T16, T11
**Reuses**: T16's ledger access and T11's parsed request envelope; the design's operation consistency and recovery sequence.
**Requirement**: PCE-37 through PCE-43; REQ-010, REQ-031.

**Tools**:

- MCP: NONE
- Skill: NONE

**Done when**:

- [ ] The canonical representation covers API version, method, canonical task target, and parsed JSON values before business normalization; object-key order and JSON whitespace do not change identity, while a changed field value or target does.
- [ ] `BEGIN IMMEDIATE` is acquired before the ledger check and before any uniqueness check.
- [ ] A repeated operation identity with the same canonical request returns the stored result without validating or applying the command again.
- [ ] A reused operation identity with a different canonical request returns a protocol conflict and preserves the original ledger entry and all task data.
- [ ] A terminal result is stored in the same transaction as its mutation, the transaction commits before any terminal response is produced, and an unexpected storage error ends the transaction without producing a terminal outcome.
- [ ] The runner is reusable by delivery 1B commands without modification.
- [ ] Integration tests cover replay of a success, replay of a rejection, identity reuse with different content, and a commit failure that is not reported as persisted.
- [ ] Gate check passes: `python -m pytest tests/server`.
- [ ] Test count: at least 16 tests pass in `tests/server/integration/test_services_runner.py` (no silent deletions).

**Tests**: integration
**Gate**: full

**Commit**: `feat(server): add transactional operation runner`

---

### T18: Implement fixed product zone configuration

**What**: Add `configure_zone` performing the atomic compare-and-set of the product time zone and returning the configuration view.
**Where**: `src/task-analyzer-server/task_analyzer_server/services.py` (modify)
**Depends on**: T14, T9
**Reuses**: T14's singleton storage and T9's clock and product date.
**Requirement**: PCE-29, PCE-30, PCE-31, PCE-35; REQ-028.

**Tools**:

- MCP: NONE
- Skill: NONE

**Done when**:

- [ ] An unknown or invalid IANA key is rejected without storing anything.
- [ ] The first valid setup persists the zone; repeating the same key returns the same configuration; a different key is refused and the retained zone is unchanged.
- [ ] Configuration setup needs no operation ledger entry, matching the approved compare-and-set contract.
- [ ] The returned view reports the configured flag, retained zone, server UTC time, and the current product date derived from that zone.
- [ ] Integration tests confirm the retained zone is unaffected by a different host or client zone.
- [ ] Gate check passes: `python -m pytest tests/server`.
- [ ] Test count: at least 10 tests pass in `tests/server/integration/test_services_configuration.py` (no silent deletions).

**Tests**: integration
**Gate**: full

**Commit**: `feat(server): add fixed product zone configuration`

---

### T19: Implement the task creation command

**What**: Add the creation command applying validation, identity assignment, server-clock creation time, and the stored terminal result.
**Where**: `src/task-analyzer-server/task_analyzer_server/services.py` (modify)
**Depends on**: T17, T15, T7
**Reuses**: T17's runner, T15's task storage, and T7's validation.
**Requirement**: PCE-01 through PCE-10, PCE-28, PCE-37, PCE-48, PCE-51, PCE-52; REQ-007, REQ-008, REQ-010, REQ-028.

**Tools**:

- MCP: NONE
- Skill: NONE

**Done when**:

- [ ] A valid title-only creation produces a pending task without observations or deadline; optional values, multiline observations, and past deadlines persist exactly as supplied.
- [ ] Creation time is sampled from the server clock after write access is acquired, and the task receives a server-generated UUID identity.
- [ ] A validation rejection stores its terminal result and creates no task.
- [ ] Success is reported only after the mutation and its result commit together.
- [ ] Integration tests carry the approved boundary fixtures through the command, including 200/201 title clusters, 5,000/5,001 observation clusters, whitespace-only titles, invalid calendar dates, combined-character cases, both accepted date endpoints, and rejected `9999-12-31`.
- [ ] Gate check passes: `python -m pytest tests/server`.
- [ ] Test count: at least 20 tests pass in `tests/server/integration/test_services_create.py` (no silent deletions).

**Tests**: integration
**Gate**: full

**Commit**: `feat(server): add task creation command`

---

### T20: Implement the pending-task edit command

**What**: Add the edit command replacing the editable state of a pending task while preserving identity, creation time, and status.
**Where**: `src/task-analyzer-server/task_analyzer_server/services.py` (modify)
**Depends on**: T19
**Reuses**: T19's shared validation and application path.
**Requirement**: PCE-11 through PCE-16, PCE-27, PCE-51, PCE-52; REQ-007, REQ-008, REQ-010, REQ-028, REQ-029.

**Tools**:

- MCP: NONE
- Skill: NONE

**Done when**:

- [ ] A valid edit persists the requested title, observations, and deadline as one full replacement of the editable fields, and clearing an optional value persists its absence.
- [ ] Task identity, original creation time, and pending status are preserved, including when the title changes.
- [ ] An edit to an absent or excluded task is a stored rejection that never creates a task; a target outside the 1A pending-edit command is a stored state rejection with no state or time change.
- [ ] A rejected edit leaves the entire persisted task unchanged, asserted by comparing the whole task before and after.
- [ ] Integration tests repeat the applicable creation boundary fixtures as edits.
- [ ] Gate check passes: `python -m pytest tests/server`.
- [ ] Test count: at least 20 tests pass in `tests/server/integration/test_services_edit.py` (no silent deletions).

**Tests**: integration
**Gate**: full

**Commit**: `feat(server): add pending task edit command`

---

### T21: Enforce uniqueness within both commands

**What**: Add in-transaction uniqueness enforcement shared by creation and editing, including the conflict rejection payload.
**Where**: `src/task-analyzer-server/task_analyzer_server/services.py` (modify)
**Depends on**: T19, T20
**Reuses**: T15's conflict lookup and the schema's unique partial indexes as the competing-write backstop.
**Requirement**: PCE-17 through PCE-27, PCE-41, PCE-42; REQ-008, REQ-029, REQ-031.

**Tools**:

- MCP: NONE
- Skill: NONE

**Done when**:

- [ ] Both commands check for a conflicting row while holding the write transaction and exclude the edited task itself.
- [ ] Dated conflicts compare against pending and completed tasks; undated conflicts compare against undated pending tasks only; deleted tasks are always excluded.
- [ ] Equivalent titles with different deadline dates coexist, and an undated task coexists with a dated task.
- [ ] A conflict is a stored rejection identifying the uniqueness conflict and the conflicting task identity, leaving both the target task and the conflicting task unchanged.
- [ ] An index violation from a competing write is translated into the same stored uniqueness rejection rather than an internal error.
- [ ] Integration tests use the protected examples and cover every comparison population named in the spec.
- [ ] Gate check passes: `python -m pytest tests/server`.
- [ ] Test count: at least 24 tests pass in `tests/server/integration/test_services_uniqueness.py` (no silent deletions).

**Tests**: integration
**Gate**: full

**Commit**: `feat(server): enforce task uniqueness in commands`

---

### T22: Compose the application and startup checks

**What**: Add `create_app` composing settings, logging, clock, services, and the router, with the approved startup verification.
**Where**: `src/task-analyzer-server/task_analyzer_server/app.py`
**Depends on**: T3, T4, T13, T14
**Reuses**: T3's settings, T4's logging, T13's connection policy, and T14's configuration read.
**Requirement**: PCE-34, PCE-35, PCE-44, PCE-45, PCE-46; REQ-003, REQ-010, REQ-027, REQ-028.

**Tools**:

- MCP: NONE
- Skill: NONE

**Done when**:

- [ ] Startup opens the configured database in existing-file mode and verifies the schema version, effective connection settings, and readable configuration.
- [ ] An absent or incompatible database fails visibly at startup; the application never initializes, migrates, or recreates a database.
- [ ] A newly initialized database with an unset product zone starts successfully and keeps the configuration endpoints usable.
- [ ] Runtime and time-data versions are logged at startup, and the clock is injectable for tests.
- [ ] No product sign-in, product account, or forwarded-identity handling is introduced.
- [ ] Tests exercise the composed application through HTTPX against disposable databases, covering successful startup, missing database, and incompatible schema version.
- [ ] Gate check passes: `python -m pytest tests/server`.
- [ ] Test count: at least 10 tests pass in `tests/server/integration/test_api_app.py` (no silent deletions).

**Tests**: e2e
**Gate**: full

**Commit**: `feat(server): compose application and startup checks`

---

### T23: Add the configuration routes

**What**: Add `GET /v1/configuration` and `PUT /v1/configuration` over the configuration service.
**Where**: `src/task-analyzer-server/task_analyzer_server/api.py`
**Depends on**: T22, T18, T12
**Reuses**: T18's configuration service and T12's response contracts.
**Requirement**: PCE-29, PCE-30, PCE-31, PCE-35; REQ-028.

**Tools**:

- MCP: NONE
- Skill: NONE

**Done when**:

- [ ] `GET` returns 200 with the configured flag, retained zone or null, server UTC time, and product date or null.
- [ ] `PUT` persists the first valid zone, returns the same configuration for a repeated identical key, returns `409 PRODUCT_TIME_ZONE_FIXED` for a different key without replacing the retained zone, and `422 INVALID_TIME_ZONE` for an unknown key.
- [ ] Responses carry `Cache-Control: no-store` and contain no business logic beyond envelope mapping.
- [ ] E2E tests cover the happy path, repeated setup, conflicting setup, and invalid zone.
- [ ] Gate check passes: `python -m pytest tests/server`.
- [ ] Test count: at least 10 tests pass in `tests/server/integration/test_api_configuration.py` (no silent deletions).

**Tests**: e2e
**Gate**: full

**Commit**: `feat(server): add configuration routes`

---

### T24: Add the task list route

**What**: Add `GET /v1/tasks` returning managed tasks with the sampled server time and product zone.
**Where**: `src/task-analyzer-server/task_analyzer_server/api.py` (modify)
**Depends on**: T22, T15, T12
**Reuses**: T15's managed-task read and T12's list response contract.
**Requirement**: PCE-30, PCE-36; REQ-010, REQ-028.

**Tools**:

- MCP: NONE
- Skill: NONE

**Done when**:

- [ ] The route returns all non-deleted tasks from a fresh committed snapshot with one sampled server time and the retained product zone per response.
- [ ] An empty collection returns an empty `items` array, and no sorting, filtering, pagination, emphasis, or metric is introduced.
- [ ] Responses carry `Cache-Control: no-store`, and array order is not asserted as a product guarantee.
- [ ] E2E tests cover an empty collection, a populated collection after creation, and exclusion of a fixture-deleted task.
- [ ] Gate check passes: `python -m pytest tests/server`.
- [ ] Test count: at least 8 tests pass in `tests/server/integration/test_api_tasks_read.py` (no silent deletions).

**Tests**: e2e
**Gate**: full

**Commit**: `feat(server): add task list route`

---

### T25: Add the task creation route

**What**: Add `POST /v1/tasks` carrying the operation envelope into the creation command.
**Where**: `src/task-analyzer-server/task_analyzer_server/api.py` (modify)
**Depends on**: T22, T19, T11
**Reuses**: T19's creation command and T11's request contracts.
**Requirement**: PCE-01 through PCE-10, PCE-19, PCE-20, PCE-26, PCE-37 through PCE-40, PCE-48, PCE-51, PCE-52; REQ-007, REQ-010, REQ-029, REQ-031.

**Tools**:

- MCP: NONE
- Skill: NONE

**Done when**:

- [ ] A valid request with an `Operation-Id` header returns `201` with the durable operation result and the created task snapshot.
- [ ] Validation rejections return `422 TASK_VALIDATION_FAILED` and uniqueness rejections `409 TASK_UNIQUENESS_CONFLICT`, both stored as terminal results.
- [ ] A task command before zone setup returns `409 PRODUCT_TIME_ZONE_REQUIRED` without recording a terminal task result.
- [ ] A repeated identical attempt returns the original stored result with its original HTTP status and creates no second task.
- [ ] E2E tests cover the approved boundary fixtures, a lost-response replay, and the before-setup case.
- [ ] Gate check passes: `python -m pytest tests/server`.
- [ ] Test count: at least 18 tests pass in `tests/server/integration/test_api_tasks_create.py` (no silent deletions).

**Tests**: e2e
**Gate**: full

**Commit**: `feat(server): add task creation route`

---

### T26: Add the task edit route

**What**: Add `PUT /v1/tasks/{task_id}` carrying the operation envelope into the pending-task edit command.
**Where**: `src/task-analyzer-server/task_analyzer_server/api.py` (modify)
**Depends on**: T25
**Reuses**: T25's envelope handling and result mapping.
**Requirement**: PCE-11 through PCE-16, PCE-23, PCE-27, PCE-41, PCE-42, PCE-51, PCE-52; REQ-007, REQ-008, REQ-010, REQ-029, REQ-031.

**Tools**:

- MCP: NONE
- Skill: NONE

**Done when**:

- [ ] A valid edit returns `200` with the durable result and the updated snapshot; identity and original creation time are unchanged in the response.
- [ ] An absent target returns `404 TASK_NOT_FOUND` and a target outside the 1A pending-edit command returns `409 TASK_STATE_INCOMPATIBLE`, both as stored rejections.
- [ ] The body replaces the whole editable form state: omitted optional values mean absent and `null` clears a value.
- [ ] Replaying an older edit after a later accepted edit returns the original stored snapshot without overwriting current task state.
- [ ] E2E tests cover acceptance, each rejection, optional clearing, and the stale-replay case.
- [ ] Gate check passes: `python -m pytest tests/server`.
- [ ] Test count: at least 16 tests pass in `tests/server/integration/test_api_tasks_edit.py` (no silent deletions).

**Tests**: e2e
**Gate**: full

**Commit**: `feat(server): add task edit route`

---

### T27: Add operation lookup and protocol error handling

**What**: Add `GET /v1/operations/{operation_id}` and the application-wide protocol and infrastructure error handlers.
**Where**: `src/task-analyzer-server/task_analyzer_server/api.py` (modify)
**Depends on**: T26
**Reuses**: The ledger read through the services layer and T12's protocol error contract.
**Requirement**: PCE-26, PCE-38, PCE-40 through PCE-43; REQ-029, REQ-031.

**Tools**:

- MCP: NONE
- Skill: NONE

**Done when**:

- [ ] Lookup returns HTTP 200 for either stored terminal outcome, carrying the original HTTP status inside the result, and `404 OPERATION_RESULT_UNKNOWN` when no committed result can be established.
- [ ] Unknown is never presented as rejection, cancellation, or rollback, and lookup's HTTP 200 never implies successful task persistence.
- [ ] `400 INVALID_OPERATION_ENVELOPE`, `409 OPERATION_ID_REUSED`, `503 STORAGE_UNAVAILABLE`, and `500 INTERNAL_ERROR` are returned as `ProtocolError` values with no terminal `outcome`, and an internal error rolls back the active transaction and logs server-side without exposing an invented result.
- [ ] A stored uniqueness rejection is returned unchanged on later consultation.
- [ ] E2E tests cover stored success lookup, stored rejection lookup, unknown lookup, unparseable JSON, an unusable operation identity, and a simulated storage failure.
- [ ] Gate check passes: `python -m pytest tests/server`.
- [ ] Test count: at least 16 tests pass in `tests/server/integration/test_api_operations.py` (no silent deletions).

**Tests**: e2e
**Gate**: full

**Commit**: `feat(server): add operation lookup and protocol errors`

---

### T28: Verify durability across restart and fresh sessions

**What**: Add the restart and fresh-session suite asserting that confirmed state and the configured zone survive a new server process.
**Where**: `tests/server/integration/test_durability.py`
**Depends on**: T22, T26, T6
**Reuses**: The initializer, the composed application, and the disposable-database fixtures from earlier tasks.
**Requirement**: PCE-34, PCE-35, PCE-36; REQ-010, REQ-028.

**Tools**:

- MCP: NONE
- Skill: NONE

**Done when**:

- [ ] A creation and an edit confirmed as persisted are still present, unchanged, after the application process is stopped and a new process starts against the same disposable database file.
- [ ] The configured product zone survives the same restart, and deadline interpretation still uses it.
- [ ] A fresh client session reads the persisted state without any client-side retention.
- [ ] The suite uses a newly allocated temporary database and can never fall back to a configured runtime database path.
- [ ] The report states plainly that a process restart is not evidence of physical power-loss durability.
- [ ] Gate check passes: `python -m pytest tests/server`.
- [ ] Test count: at least 8 tests pass in `tests/server/integration/test_durability.py` (no silent deletions).

**Tests**: integration
**Gate**: full

**Commit**: `test(server): verify restart and fresh session durability`

---

### T29: Verify concurrency and fault-injection behaviour

**What**: Add the concurrency and failure suite for overlapping attempts, conflicting operations, and crash points around commit.
**Where**: `tests/server/integration/test_concurrency.py`
**Depends on**: T28
**Reuses**: T28's process fixtures and the disposable-database helpers.
**Requirement**: PCE-19, PCE-20, PCE-27, PCE-37, PCE-39, PCE-42, PCE-43; REQ-010, REQ-029, REQ-031.

**Tools**:

- MCP: NONE
- Skill: NONE

**Done when**:

- [ ] Two simultaneous copies of one attempt, run on independent connections with explicit synchronization rather than sleeps, apply the operation exactly once; the second observes the first terminal result.
- [ ] Two distinct operations that conflict under uniqueness never both produce an accepted resulting task, and neither is treated as a replay of the other.
- [ ] A stop before commit leaves no committed partial task and result pair, and the same attempt repeated afterwards can still establish a result.
- [ ] A stop after commit but before the response leaves the original outcome discoverable and is never applied twice.
- [ ] A lock timeout or storage failure surfaces as an infrastructure error with no invented terminal result, and lookup during in-flight work returns unknown rather than rejection.
- [ ] Gate check passes: `python -m pytest tests/server`.
- [ ] Test count: at least 12 tests pass in `tests/server/integration/test_concurrency.py` (no silent deletions).

**Tests**: integration
**Gate**: full

**Commit**: `test(server): verify concurrency and failure handling`

---

### T30: Add the systemd service asset

**What**: Add the proposed systemd unit for the supervised Uvicorn process.
**Where**: `docs/architecture/deployment/task-analyzer-server.service`
**Depends on**: T3, T22
**Reuses**: T3's environment variable names and T22's application entry point; the design's runtime proposal.
**Requirement**: PCE-44, PCE-45; REQ-003.

**Tools**:

- MCP: NONE
- Skill: NONE

**Done when**:

- [ ] The unit runs one Uvicorn worker on `127.0.0.1:8000` with no development reload, under a dedicated unprivileged `task-analyzer` account.
- [ ] It declares a writable state directory, a read-only installed application, restart-on-failure supervision, and the approved environment variables.
- [ ] No real host name, credential, tailnet rule, or deployment step is executed by this task; the asset is a file only.
- [ ] Gate check passes: the Build gate is run for the phase; the asset itself is not a lint or type target.

**Tests**: none
**Gate**: build

**Commit**: `chore(deploy): add systemd service asset`

---

### T31: Add the deployment and private-access guide

**What**: Add the server deployment document covering installation, explicit database initialization, private access, and the verification checklist.
**Where**: `docs/architecture/deployment/server.md`
**Depends on**: T30, T6
**Reuses**: T30's unit file, T6's initializer, and the design's private-access proposal.
**Requirement**: PCE-44 through PCE-47; REQ-003, REQ-027.

**Tools**:

- MCP: NONE
- Skill: NONE

**Done when**:

- [ ] The document covers the virtual environment installation on Ubuntu Server 26.04.1 LTS, the locked requirements, the explicit one-time database initialization step, and the service installation.
- [ ] It documents Tailscale Serve as the tailnet-only HTTPS front end for the loopback listener, a dedicated tailnet device name, and desktop device access, with no product sign-in.
- [ ] It states that the actual tailnet hostname, device identifiers, interpreter version set, and host paths must be confirmed in an authorized environment, and that running any step requires explicit deployment authorization.
- [ ] It carries the pending confirmation handed over by T2: the locked dependency set must be re-checked against the interpreter actually installed on the target before the service is considered deployable.
- [ ] It records that the target is the user's own server, not a disposable validation host: every install, service, and Tailscale step needs authorization at the time it is run, the first `initialize_database` call is authorized separately, and existing state is backed up before it.
- [ ] The private-access acceptance check for PCE-46 and PCE-47 is recorded as a pending authorized-environment verification, not as a performed check.
- [ ] It ends with an `Open questions` section, per the repository document rule.
- [ ] Gate check passes: the Build gate is run for the phase; links and scope boundaries are checked against the approved documents.

**Tests**: none
**Gate**: build

**Commit**: `docs(deploy): add server deployment and access guide`

---

## Phase Execution Map

Phases run in sequence; tasks within a phase run in order. Execution is strictly sequential - there is no intra-phase parallelism.

```
Phase 1 → Phase 2 → Phase 3 → Phase 4 → Phase 5 → Phase 6 → Phase 7 → Phase 8 → Phase 9
```

Intra-phase ordering:

```
Phase 1:  T1 → T2 → T3
Phase 1:  T2 → T4
Phase 2:  T5 → T6
Phase 3:  T7 → T8
Phase 3:  T9 → T10
Phase 4:  T11 → T12
Phase 5:  T13 → T14
Phase 5:  T13 → T15
Phase 5:  T13 → T16
Phase 6:  T17 → T19 → T20 → T21
Phase 6:  T19 → T21
Phase 7:  T22 → T23
Phase 7:  T22 → T24
Phase 7:  T22 → T25 → T26 → T27
Phase 8:  T28 → T29
Phase 9:  T30 → T31
```

Cross-phase dependency edges, drawn explicitly so the diagram and the task bodies stay in parity:

```
T2 → T5
T2 → T7
T2 → T9
T7 → T11
T6 → T13
T8 → T15
T12 → T16
T16 → T17
T11 → T17
T14 → T18
T9 → T18
T15 → T19
T7 → T19
T3 → T22
T4 → T22
T13 → T22
T14 → T22
T18 → T23
T12 → T23
T15 → T24
T12 → T24
T19 → T25
T11 → T25
T22 → T28
T26 → T28
T6 → T28
T3 → T30
T22 → T30
T6 → T31
```

**Execution packing**: 31 tasks pack into five task-budgeted batches on phase boundaries - Phases 1-2 (6 tasks), Phase 3-4 (6 tasks), Phase 5 (4 tasks), Phase 6 (5 tasks), Phase 7 (6 tasks), Phases 8-9 (4 tasks). Because this exceeds one batch, Execute must present the sub-agent offer before dispatching, and the user decides. Batches run sequentially; no batch starts before the previous one reports every task complete. After the final task, the independent Verifier runs automatically and writes `validation.md`.

---

## Task Granularity Check

| Task | Scope | Status |
| --- | --- | --- |
| T1, T2 | 1 configuration file / 1 requirements set | Granular |
| T3, T4 | 1 module each | Granular |
| T5, T6 | 1 DDL asset / 1 initializer | Granular |
| T7, T8 | 1 function each in `domain.py` | Granular |
| T9, T10 | 1 cohesive clock unit / 1 cutoff function in `clock.py` | Granular |
| T11, T12 | 1 cohesive model group each in `contracts.py` | Granular |
| T13, T14, T15, T16 | 1 cohesive access concern each in `storage.py` | Granular |
| T17, T18, T19, T20, T21 | 1 service operation or enforcement rule each in `services.py` | Granular |
| T22 | 1 composition module | Granular |
| T23, T24, T25, T26, T27 | 1 route group each in `api.py` | Granular |
| T28, T29 | 1 cross-cutting scenario suite each | Granular |
| T30, T31 | 1 deployment asset / 1 document | Granular |

Every task names exactly one file in `Where`. Tasks that share a module (`domain.py`, `clock.py`, `contracts.py`, `storage.py`, `services.py`, `api.py`) are split at cohesive responsibility seams, which the skill permits for two or three related things in the same file.

---

## Diagram-Definition Cross-Check

| Task | Depends On (task body) | Diagram Shows | Status |
| --- | --- | --- | --- |
| T1 | None | no incoming arrow | Match |
| T2 | T1 | T1 → T2 | Match |
| T3 | T2 | T2 → T3 | Match |
| T4 | T2 | T2 → T4 | Match |
| T5 | T2 | T2 → T5 | Match |
| T6 | T5 | T5 → T6 | Match |
| T7 | T2 | T2 → T7 | Match |
| T8 | T7 | T7 → T8 | Match |
| T9 | T2 | T2 → T9 | Match |
| T10 | T9 | T9 → T10 | Match |
| T11 | T7 | T7 → T11 | Match |
| T12 | T11 | T11 → T12 | Match |
| T13 | T6 | T6 → T13 | Match |
| T14 | T13 | T13 → T14 | Match |
| T15 | T13, T8 | T13 → T15, T8 → T15 | Match |
| T16 | T13, T12 | T13 → T16, T12 → T16 | Match |
| T17 | T16, T11 | T16 → T17, T11 → T17 | Match |
| T18 | T14, T9 | T14 → T18, T9 → T18 | Match |
| T19 | T17, T15, T7 | T17 → T19, T15 → T19, T7 → T19 | Match |
| T20 | T19 | T19 → T20 | Match |
| T21 | T19, T20 | T19 → T21, T20 → T21 | Match |
| T22 | T3, T4, T13, T14 | T3 → T22, T4 → T22, T13 → T22, T14 → T22 | Match |
| T23 | T22, T18, T12 | T22 → T23, T18 → T23, T12 → T23 | Match |
| T24 | T22, T15, T12 | T22 → T24, T15 → T24, T12 → T24 | Match |
| T25 | T22, T19, T11 | T22 → T25, T19 → T25, T11 → T25 | Match |
| T26 | T25 | T25 → T26 | Match |
| T27 | T26 | T26 → T27 | Match |
| T28 | T22, T26, T6 | T22 → T28, T26 → T28, T6 → T28 | Match |
| T29 | T28 | T28 → T29 | Match |
| T30 | T3, T22 | T3 → T30, T22 → T30 | Match |
| T31 | T30, T6 | T30 → T31, T6 → T31 | Match |

No task depends on a task in a later phase.

---

## Test Co-location Validation

| Task | Code Layer Created/Modified | Matrix Requires | Task Says | Status |
| --- | --- | --- | --- | --- |
| T1 | Packaging | none | none | OK |
| T2 | Packaging | none | none | OK |
| T3 | Runtime configuration | unit | unit | OK |
| T4 | Runtime configuration | unit | unit | OK |
| T5 | Persistence (DDL) | integration | integration | OK |
| T6 | Persistence | integration | integration | OK |
| T7 | Domain rules | unit | unit | OK |
| T8 | Domain rules | unit | unit | OK |
| T9 | Domain rules | unit | unit | OK |
| T10 | Domain rules | unit | unit | OK |
| T11 | Wire contracts | unit | unit | OK |
| T12 | Wire contracts | unit | unit | OK |
| T13 | Persistence | integration | integration | OK |
| T14 | Persistence | integration | integration | OK |
| T15 | Persistence | integration | integration | OK |
| T16 | Persistence | integration | integration | OK |
| T17 | Operation services | integration | integration | OK |
| T18 | Operation services | integration | integration | OK |
| T19 | Operation services | integration | integration | OK |
| T20 | Operation services | integration | integration | OK |
| T21 | Operation services | integration | integration | OK |
| T22 | API composition | e2e | e2e | OK |
| T23 | API | e2e | e2e | OK |
| T24 | API | e2e | e2e | OK |
| T25 | API | e2e | e2e | OK |
| T26 | API | e2e | e2e | OK |
| T27 | API | e2e | e2e | OK |
| T28 | Cross-cutting scenario suite over services and API | integration | integration | OK |
| T29 | Cross-cutting scenario suite over services and API | integration | integration | OK |
| T30 | Deployment asset | none | none | OK |
| T31 | Deployment document | none | none | OK |

`Tests: none` appears only where the matrix says none for that layer. No task defers its tests to a later task. T28 and T29 add no production code; they carry the restart, concurrency, and failure scenarios that span several modules and become runnable only once the API exists.

---

## Requirement Coverage of the Tasks

| Criterion group | Tasks that carry it |
| --- | --- |
| PCE-01 through PCE-10, PCE-48, PCE-51, PCE-52 (creation and field bounds) | T7, T11, T19, T25 |
| PCE-11 through PCE-16 (pending edits) | T7, T15, T20, T26 |
| PCE-17 through PCE-27 (uniqueness) | T5, T8, T15, T21, T25, T26, T29 |
| PCE-28 through PCE-33, PCE-49, PCE-50, PCE-51, PCE-52 (time, zone, cutoff) | T9, T10, T14, T18, T23 |
| PCE-34, PCE-35, PCE-36 (durability and fresh sessions) | T6, T22, T24, T28 |
| PCE-37 through PCE-43 (operation outcomes and recovery) | T13, T16, T17, T25, T26, T27, T29 |
| PCE-44 through PCE-47 (runtime and private access) | T1, T2, T3, T22, T30, T31 |

Every 1A criterion is carried by at least one task. PCE-46 and PCE-47 are only partly verifiable locally: T22 proves there is no product sign-in, while the private tailnet access check stays a pending verification in an explicitly authorized environment, recorded as such in T31 and in the Verifier's report.

## Open questions

- Deployment values - the actual tailnet hostname, device identifiers, installed interpreter version set, and host paths - remain unconfirmed and require an authorized environment. No task executes deployment, database initialization on a real host, or Tailscale configuration.
- Exact dependency versions are resolved and pinned in T2 rather than assumed here. An incompatibility with the Python 3.13 baseline returns to Design as a revision proposal.
- Whether Execute runs inline or with batch sub-agents is decided at Execute time, after the offer.

# Persistent Task Creation and Editing Validation

## Validation: persistent-task-creation-editing - FAIL

**Verdict: FAIL.** The audit reproduced four functional defects and one runtime logging defect despite passing local regression gates. Delivery 1A also remains blocked on the previously recorded target-interpreter and private-access evidence.

**Date:** 2026-09-14.
**Spec:** [Approved delivery 1A specification](spec.md).
**Design:** [Approved baseline and audit revision](design.md).
**Diff reviewed:** `127d777..aa59004`, 56 changed files, 17,856 insertions and 276 deletions, plus the working tree's three initially untracked `__pycache__/` directories. Application and test files were unchanged by the audit.
**Audit branch:** `docs/1a-code-audit`, initially at `aa59004`.
**Verifier:** independent TLC Verifier sub-agent, separate from the implementation author; the root auditor supplied reproductions, which the Verifier inspected and independently reran.
**Artifacts:** this report and script-managed lessons only; the root auditor owns the separate STATE Handoff update. No implementation/test edits, commits, remote actions, deployment, or real-database changes occurred.

The independent Verifier completed its review, reproductions, gates, sensor and report draft before its session ran out of credits. The root auditor finalized citation corrections, lesson recording and the completion-gate check.

## Findings

### F1: Concurrent initialization can delete the successfully initialized database (P1)

**Evidence:** `src/task-analyzer-server/task_analyzer_server/schema.py:54` checks existence before connecting, while `schema.py:66` handles a later SQLite failure by deleting the path. Two invocations can both observe an absent path. The first initializes successfully; the second opens that same database, fails on `CREATE TABLE`, and deletes the first invocation's database. The cleanup does not establish ownership of the file.

**Reproduction:** allocate one new file path inside a temporary directory; use two threads and a barrier inside the existing `read_initial_schema` call so both pass the real existence check; pause the second until the first initializer returns, then resume it. Both execute the unchanged initializer and real SQLite operations. Observed output:

```text
winner: initialized; exists=True
loser: OperationalError: table schema_version already exists
database_exists_after_both_attempts=False
```

The losing invocation can therefore remove a database that another successful invocation has already made available. This violates T6's refusal to overwrite/reinitialize existing state and the database preservation rules; it jeopardizes REQ-010/PCE-34 persistence if the winner starts serving work before the loser resumes. Existing initializer tests exercise an already-existing file, but miss concurrent ownership.

**Proposed fix task:** atomically acquire exclusive ownership of a new database path, and delete a failed partial initialization only when it belongs to that invocation. Change `schema.py` and add isolated concurrency regressions in `test_schema_init.py`. **Done when:** two synchronized initializers leave exactly one successful, readable schema; the loser cannot remove or alter it, including a row committed after the winner returns; existing-file refusal and failure cleanup remain intact. **Gate:** the full Build gate. Scope requires approval before implementation.

### F2: SQLite work blocks the application's event loop (P2)

**Evidence:** async handlers directly invoke synchronous services at `src/task-analyzer-server/task_analyzer_server/api.py:151`, `api.py:183`, and `api.py:217`. The services open SQLite connections, execute `BEGIN IMMEDIATE`, and may wait for the configured busy timeout on the event-loop thread. The approved design assigns blocking database work to a synchronous worker invocation and deploys one Uvicorn worker.

**Reproduction:** hold `BEGIN IMMEDIATE` on a separate connection to a disposable configured database; set the application busy timeout to 300 ms; schedule an event-loop callback for 20 ms and submit an ASGI POST. The POST returns `503`; the 20 ms callback executes only after **396 ms** in the Verifier's run. No service delay was mocked. With the approved default 5,000 ms timeout, one waiting write can prevent unrelated requests, including result consultation, from being dispatched during that interval.

**Proposed fix task:** await request parsing and move each complete synchronous service invocation to the framework's worker thread facility, keeping connection open/use/close together. Change `api.py` and the HTTP concurrency tests. **Done when:** a blocked POST/PUT/configuration write returns the existing infrastructure contract after its timeout while another HTTP read or event-loop probe completes before that timeout; same-attempt and uniqueness concurrency remain correct. **Gate:** the full Build gate. Trace: T22-T26/T29, the Design connection-ownership rule, PCE-38/PCE-43 and REQ-031.

### F3: Invalid JSON numbers escape validation as internal errors (P2)

**Evidence:** `src/task-analyzer-server/task_analyzer_server/api.py:371` uses permissive `json.loads`. `services.py:805` later canonicalizes with `allow_nan=False` outside the business validation flow. `NaN`/`Infinity` are accepted by that parser; the valid JSON numeric spelling `1e309` becomes infinity in a Python float. Canonicalization then raises `ValueError`, mapped to `500 INTERNAL_ERROR` instead of the approved protocol/validation result.

**Reproduction:** after configuring a disposable application, POST each body with a fresh valid Operation-Id:

```text
{"title":NaN}                       -> 500 INTERNAL_ERROR; lookup 404
{"title":1e309}                     -> 500 INTERNAL_ERROR; lookup 404
{"title":"ok","deadline":Infinity} -> 500 INTERNAL_ERROR; lookup 404
```

The Design explicitly rejects invalid JSON numbers. Non-JSON constants belong to `400 INVALID_OPERATION_ENVELOPE` without a terminal result; a syntactically valid JSON number in a string-only task field belongs to the durable `422 TASK_VALIDATION_FAILED` / `INVALID_FIELD_TYPE` flow. The current response instead leaves the client with an unknown operation. Existing malformed-JSON and strict-field tests omit these parser/canonicalization cases. A lone escaped surrogate also produced 500 during exploratory probing; it is not an additional approved text restriction or a separate finding here.

**Proposed fix task:** reject non-JSON constants at the HTTP boundary and ensure supported parsed JSON numbers cannot fail canonicalization before the durable field-validation flow. Change `api.py` and, if necessary, canonicalization in `services.py`, with creation/editing HTTP regressions. **Done when:** NaN and both infinities produce the specified protocol response and no ledger entry; valid numeric wrong-type values, including the overflow example, produce an exactly consultable durable rejection; no task changes occur, and replay identity semantics remain intact. **Gate:** the full Build gate. Trace: T11/T22/T25/T26, the Design Values and responses/error contracts, REQ-007/008/031 and PCE-15.

### F4: Task-list metadata and items are read from different snapshots (P2)

**Evidence:** `src/task-analyzer-server/task_analyzer_server/services.py:393` reads the configured zone and `services.py:394` reads tasks without a read transaction. Connections run in autocommit, so the SELECTs need not observe the same committed state, contrary to the Design and the function's own contract.

**Reproduction:** initialize an unset disposable database. Pause a list reader immediately after its real zone SELECT returns `None`. On another connection perform real zone setup to UTC and create a task; then resume the reader's real task SELECT. Observed response values:

```text
items=1
product_time_zone=None
product_date=None
```

No committed state ever contained that combination: task creation requires configured product time. This is an initial-setup overlap, not a claim that the fixed zone can later change.

**Proposed fix task:** enclose the configuration and task reads in one explicit read transaction, with normal rollback/close handling and one sampled server instant. Change `services.py`/the appropriate storage helper and `test_api_tasks_read.py`. **Done when:** the synchronized scenario returns either the complete pre-setup empty view or the complete post-setup configured view, never mixed metadata/items; ordinary reads remain fresh and `Cache-Control: no-store`. **Gate:** the full Build gate. Trace: T24, Design committed-snapshot contract, PCE-30/PCE-36 and REQ-010/028.

### F5: The documented Uvicorn launch still emits non-JSON logs (P3)

**Evidence:** `src/task-analyzer-server/task_analyzer_server/logging_config.py:93` through `logging_config.py:99` configure only the root logger. Uvicorn's default logging configuration installs its own handler with propagation disabled. The service asset uses that default configuration. Application root logs are structured, but the runtime output is a mixture of JSON and plain text despite the Design/deployment JSON-line claim.

**Reproduction:** construct `uvicorn.Config('task_analyzer_server.app:application_factory', factory=True)`, call the real `configure_logging('INFO')`, capture the existing Uvicorn handler stream, and log `uvicorn.error.info('Application startup complete.')`. The Verifier independently observed:

```text
UVICORN_LOG 'INFO:     Application startup complete.\n'
JSON_VALID False
UVICORN_PROPAGATE False
```

**Proposed fix task:** apply the approved logging configuration to the actual runtime logger hierarchy/launch path, avoiding duplicate handlers. Cover real Uvicorn configuration rather than only standalone formatter calls. **Done when:** application, access, startup, and error records in the documented launch path are JSON lines with the applicable schema and no task bodies/text or secrets. **Gate:** full Build and an installed-runtime logging smoke check. Trace: T4/T22/T30, Design Runtime, Private Access, and Logging; no new product observability feature is proposed.

### External completion gaps remain open

- **PCE-44 / REQ-003:** the Python 3.13 declaration and local interpreter are verified; the actual Ubuntu target interpreter and its target-specific lock/gates remain unverified.
- **PCE-47 / REQ-027:** no authorized private Tailscale path has been exercised. The guide and local absence of product sign-in cannot establish private reachability.

These were already open before this audit. They are independent of F1-F5 and need the separately authorized host session. No host or real database was touched.

## Task completion and approval boundary

All 31 original tasks are marked Complete in [tasks.md](tasks.md). Those task labels report implementation history, not proof that all Done-when branches hold. F1-F5 are new, concrete local gaps against that approved scope. They replace the previous report's conclusion that no local work remains. Fix proposals above are reviewable audit output; this audit does not execute them or change task/spec approval records.

## Gate check

The PATH interpreter lacked pytest, Ruff, and mypy. Those initial invocations were unavailable-environment results, not code failures. A fresh temporary CPython **3.13.2** development environment was then installed from `requirements/dev-py313.txt` using `--require-hashes` (exit 0); no dependency was upgraded or added. Source-suite imports used the repository package root through PYTHONPATH; installed-wheel checks explicitly removed that fallback.

| Gate | Actual command | Exit | Evidence |
| --- | --- | --- | --- |
| Formatting | `python -m ruff format --check src/task-analyzer-server tests/server` | 0 | 40 files already formatted |
| Lint | `python -m ruff check src/task-analyzer-server tests/server` | 0 | All checks passed |
| Types | `python -m mypy --strict src/task-analyzer-server/task_analyzer_server` | 0 | 11 source files, no issues |
| Regression suite | `python -m pytest tests/server` | 0 | **588 passed**, 0 failed, 0 skipped, 59.64 s |
| Dependency consistency | `python -m pip check` | 0 | No broken requirements found |
| Full build | `python -m build --no-isolation` in an isolated copy of actual package sources | 0 | sdist and wheel built using the locked backend |
| Installed distribution | Suite `test_installed_distribution.py`; additionally install/import the full-build wheel in a fresh runtime environment | 0 | Packaged schema, disposable initialization, factory startup, absent-database refusal, and process restart; no editable import |
| Spec structure | `python .ai/skills/tlc-spec-driven/scripts/validate_spec.py persistent-task-creation-editing` | 0 | 0 errors, 0 warnings |
| Task structure | `python .ai/skills/tlc-spec-driven/scripts/validate_tasks.py persistent-task-creation-editing` | 0 | 0 errors, 5 reviewed warnings |
| Feature completion | `python .ai/skills/tlc-spec-driven/scripts/validate_state.py persistent-task-creation-editing` | 1 | Expected: this evidence-backed report is FAIL; the feature is not complete |

The task warnings concern Tests:none on T1/T2/T30/T31 (the approved matrix permits it) and T22's two-file HTTP composition task (explicitly justified by Design/Tasks). The two test warnings are existing Starlette/HTTPX and AnyIO deprecations; they were not suppressed and do not authorize adding a library. Build byte-compilation warnings result from audit isolation using `PYTHONDONTWRITEBYTECODE=1`.

Runtime data recorded by the hash lock: FastAPI 0.141.1, Starlette 1.6.0, Pydantic 2.13.5, Uvicorn 0.52.4, regex 2026.9.10, tzdata 2026.4, pytest 9.1.1. This Windows run establishes no Ubuntu compatibility claim.

**Test integrity:** baseline `127d777` has no server tests; current suite has 588. The implementation added tests (+588); no existing protected scenario was modified in this audit. The scratch's independent full baseline also passed all 588 tests (57.58 s). No test was skipped or weakened to obtain a passing gate. A process restart/crash test is not evidence of physical power-loss durability.

## Spec-anchored acceptance evidence

The following map was checked against the approved outcomes, the actual test bodies, and the executed suite. Each reference cites an assertion line. **Covered** means that the named regression scenario asserts the required value/state; it does not claim exhaustive proof of the criterion or override F1-F5. Fifty criteria have local scenario coverage, PCE-44 has local evidence plus an external gap, and PCE-47 has no actual access evidence. No new behavioral default or spec-precision change is proposed.

| Criterion | Required outcome | Actual assertion evidence | Local scenario result |
| --- | --- | --- | --- |
| PCE-01 | Title-only creation is pending with absent optional fields | `tests/server/integration/test_services_create.py:187` — `result.outcome == 'succeeded'`; `tests/server/integration/test_services_create.py:191` — `result.task.observations is None`; `tests/server/integration/test_services_create.py:192` — `result.task.deadline is None`; `tests/server/integration/test_services_create.py:193` — `result.task.status == 'pending'` | Covered |
| PCE-02 | Empty and whitespace-only title rejected | `tests/server/unit/test_domain_validation.py:84` — `issues_for(title='') == (REQUIRED_TITLE,)` | Covered |
| PCE-03 | Exactly 200 characters after edge trimming accepted | `tests/server/unit/test_domain_validation.py:155` — `issues_for(title=f"   {'a' * 200}   ") == ()` | Covered |
| PCE-04 | 201 title characters rejected | `tests/server/unit/test_domain_validation.py:124` — `issues_for(title='a' * 201) == (TOO_LONG_TITLE,)` | Covered |
| PCE-05 | 5,000 observation characters accepted | `tests/server/unit/test_domain_validation.py:178` — `issues_for(observations='a' * 5000) == ()` | Covered |
| PCE-06 | 5,001 observation characters rejected | `tests/server/unit/test_domain_validation.py:183` — `issues_for(observations='a' * 5001) == (TOO_LONG_OBSERVATIONS,)` | Covered |
| PCE-07 | Observation line breaks persist unchanged | `tests/server/integration/test_services_create.py:217` — `stored_tasks(settings)[0].observations == observations` | Covered |
| PCE-08 | The supplied calendar date persists | `tests/server/integration/test_services_create.py:206` — `stored[0].deadline == date(2026, 9, 14)` | Covered |
| PCE-09 | A valid past deadline is accepted and stored | `tests/server/integration/test_services_create.py:226` — `result.outcome == 'succeeded'`; `tests/server/integration/test_services_create.py:227` — `stored_tasks(settings)[0].deadline == date(2020, 1, 31)` | Covered |
| PCE-10 | Non-calendar dates rejected | `tests/server/unit/test_domain_validation.py:283` — `issues_for(deadline=deadline) == (INVALID_DEADLINE,)` | Covered |
| PCE-11 | All editable fields persist together | `tests/server/integration/test_services_edit.py:310` — `result.outcome == 'succeeded'`; `tests/server/integration/test_services_edit.py:314` — `stored.title == NEW_TITLE`; `tests/server/integration/test_services_edit.py:315` — `stored.observations == 'Replaced'`; `tests/server/integration/test_services_edit.py:316` — `stored.deadline == date(2026, 9, 20)` | Covered |
| PCE-12 | Editing retains task identity | `tests/server/integration/test_services_edit.py:374` — `result.task.task_id == task_id` | Covered |
| PCE-13 | Editing retains original creation time | `tests/server/integration/test_services_edit.py:390` — `stored.created_at == SERVER_NOW` | Covered |
| PCE-14 | Editing retains pending status and no completion time | `tests/server/integration/test_services_edit.py:376` — `result.task.status == 'pending'`; `tests/server/integration/test_services_edit.py:377` — `result.task.completed_at is None` | Covered |
| PCE-15 | Invalid edit rejects and preserves all stored columns | `tests/server/integration/test_services_edit.py:494` — `result.outcome == 'rejected'`; `tests/server/integration/test_services_edit.py:495` — `result.original_http_status == 422`; `tests/server/integration/test_services_edit.py:497` — `result.error.fields == (REQUIRED_TITLE,)`; `tests/server/integration/test_services_edit.py:498` — `stored_columns(settings, task_id) == before` | Covered |
| PCE-16 | Removing optional fields persists absence | `tests/server/integration/test_services_edit.py:329` — `stored.observations is None`; `tests/server/integration/test_services_edit.py:330` — `stored.deadline is None` | Covered |
| PCE-17 | Protected case/space title examples compare equal | `tests/server/unit/test_domain_title_key.py:26` — `title_key('Read notes') == title_key(' READ  NOTES ')` | Covered |
| PCE-18 | Protected accented and unaccented title examples differ | `tests/server/unit/test_domain_title_key.py:31` — `title_key(ACCENTED_TITLE) != title_key(PLAIN_TITLE)` | Covered |
| PCE-19 | Dated uniqueness includes completed tasks | `tests/server/integration/test_services_uniqueness.py:412` — `result.outcome == 'rejected'`; `tests/server/integration/test_services_uniqueness.py:414` — `result.error.conflicting_task_id == completed` | Covered |
| PCE-20 | Undated pending equivalent title conflicts | `tests/server/integration/test_services_uniqueness.py:473` — `result.outcome == 'rejected'`; `tests/server/integration/test_services_uniqueness.py:475` — `result.error.code == ErrorCode.TASK_UNIQUENESS_CONFLICT`; `tests/server/integration/test_services_uniqueness.py:476` — `result.error.conflicting_task_id == existing` | Covered |
| PCE-21 | Equivalent titles on different dates coexist | `tests/server/integration/test_services_uniqueness.py:425` — `result.outcome == 'succeeded'`; `tests/server/integration/test_services_uniqueness.py:426` — `len(stored_tasks(settings)) == 2` | Covered |
| PCE-22 | Dated and undated equivalent titles coexist | `tests/server/integration/test_services_uniqueness.py:437` — `result.outcome == 'succeeded'`; `tests/server/integration/test_services_uniqueness.py:438` — `len(stored_tasks(settings)) == 2` | Covered |
| PCE-23 | Editing excludes the target itself | `tests/server/integration/test_services_uniqueness.py:599` — `result.outcome == 'succeeded'`; `tests/server/integration/test_services_uniqueness.py:601` — `result.task.title == EQUIVALENT_TITLE` | Covered |
| PCE-24 | Deleted tasks do not block equivalent creation | `tests/server/integration/test_services_uniqueness.py:500` — `result.outcome == 'succeeded'` | Covered |
| PCE-25 | Completed undated tasks do not block pending creation | `tests/server/integration/test_services_uniqueness.py:489` — `result.outcome == 'succeeded'` | Covered |
| PCE-26 | Uniqueness rejection names the conflicting task | `tests/server/integration/test_services_uniqueness.py:376` — `result.error.conflicting_task_id == existing` | Covered |
| PCE-27 | Rejected conflicting edit preserves both tasks entirely | `tests/server/integration/test_services_uniqueness.py:574` — `stored_columns(settings, existing) == existing_before`; `tests/server/integration/test_services_uniqueness.py:575` — `stored_columns(settings, edited) == edited_before` | Covered |
| PCE-28 | Creation instant comes from server clock when applied | `tests/server/integration/test_services_create.py:448` — `result.task.created_at == SERVER_NOW`; `tests/server/integration/test_services_create.py:449` — `stored_tasks(settings)[0].created_at == SERVER_NOW` | Covered |
| PCE-29 | Initial product zone is retained | `tests/server/integration/test_services_configuration.py:140` — `view.configured is True`; `tests/server/integration/test_services_configuration.py:141` — `view.product_time_zone == PRODUCT_ZONE`; `tests/server/integration/test_services_configuration.py:142` — `retained_zone(settings) == PRODUCT_ZONE` | Covered |
| PCE-30 | Product date uses server time and configured zone | `tests/server/integration/test_services_configuration.py:151` — `view.server_now == SERVER_NOW`; `tests/server/integration/test_services_configuration.py:152` — `view.product_date == PRODUCT_DATE_IN_SAO_PAULO` | Covered |
| PCE-31 | A changed desktop zone cannot replace the product zone | `tests/server/integration/test_services_configuration.py:253` — `retained_zone(settings) == PRODUCT_ZONE` | Covered |
| PCE-32 | September 14 cutoff is September 15 local midnight | `tests/server/unit/test_clock_cutoff.py:71` — `cutoff == SEPTEMBER_15_MIDNIGHT`; `tests/server/unit/test_clock_cutoff.py:72` — `cutoff.astimezone(SAO_PAULO) == datetime(2026, 9, 15, 0, 0, tzinfo=SAO_PAULO)` | Covered |
| PCE-33 | At cutoff, the pending deadline is overdue without grace | `tests/server/unit/test_clock_cutoff.py:89` — `midnight == cutoff`; `tests/server/unit/test_clock_cutoff.py:90` — `midnight >= cutoff` | Covered |
| PCE-34 | Accepted edited state survives a new server process | `tests/server/integration/test_durability.py:388` — `edited.status_code == 200`; `tests/server/integration/test_durability.py:389` — `survivor == edited.json()['task']` | Covered |
| PCE-35 | Configured zone survives process restart | `tests/server/integration/test_durability.py:417` — `configuration['configured'] is True`; `tests/server/integration/test_durability.py:418` — `configuration['product_time_zone'] == PRODUCT_ZONE` | Covered |
| PCE-36 | A fresh client reads persisted task identity and zone | `tests/server/integration/test_durability.py:465` — `'set-cookie' not in reading.headers`; `tests/server/integration/test_durability.py:466` — `reading.json()['product_time_zone'] == PRODUCT_ZONE`; `tests/server/integration/test_durability.py:467` — `[item['task_id'] for item in reading.json()['items']] == [created.json()['task']['task_id']]` | Covered |
| PCE-37 | A failed commit is not reported as persisted | `tests/server/integration/test_services_runner.py:503` — `services.lookup_operation(settings, operation_id) is None`; `tests/server/integration/test_services_runner.py:504` — `read_tasks(settings) == ()` | Covered |
| PCE-38 | Consultation returns the retained original result | `tests/server/integration/test_services_runner.py:517` — `services.lookup_operation(settings, operation_id) == original` | Covered |
| PCE-39 | Repetition returns original result and creates only once | `tests/server/integration/test_services_runner.py:356` — `repeated == original`; `tests/server/integration/test_services_runner.py:357` — `command.runs == 1`; `tests/server/integration/test_services_runner.py:358` — `[task.task_id for task in read_tasks(settings)] == [task_id]` | Covered |
| PCE-40 | Original operation is consultable after response/session loss and restart | `tests/server/integration/test_durability.py:484` — `consulted.status_code == 200`; `tests/server/integration/test_durability.py:485` — `consulted.json() == original.json()` | Covered |
| PCE-41 | Original uniqueness rejection remains consultable | `tests/server/integration/test_services_uniqueness.py:523` — `services.lookup_operation(settings, request.operation_id) == result`; `tests/server/integration/test_services_uniqueness.py:526` — `result.outcome == 'rejected'` | Covered |
| PCE-42 | Different conflicting action rejects under its own identity | `tests/server/integration/test_services_uniqueness.py:540` — `refused.outcome == 'rejected'`; `tests/server/integration/test_services_uniqueness.py:541` — `refused.operation_id == second.operation_id`; `tests/server/integration/test_services_uniqueness.py:543` — `refused.error.code == ErrorCode.TASK_UNIQUENESS_CONFLICT`; `tests/server/integration/test_services_uniqueness.py:544` — `len(stored_tasks(settings)) == 1` | Covered |
| PCE-43 | Unknown is distinct from a terminal rejection | `tests/server/integration/test_api_operations.py:280` — `response.status_code == 404`; `tests/server/integration/test_api_operations.py:281` — `response.json()['error']['code'] == ErrorCode.OPERATION_RESULT_UNKNOWN.value` | Covered |
| PCE-44 | Declared minimum is Python 3.13; actual target still pending | `tests/server/unit/test_packaging_metadata.py:46` — `declared_floor() == APPROVED_FLOOR` | Partial: local only |
| PCE-45 | Dedicated self-hosting from an installed distribution | `tests/server/integration/test_installed_distribution.py:465` and `tests/server/integration/test_installed_distribution.py:503`: installed initializer and restart assertions; actual full-build wheel import and isolated initializer also passed in this audit | Covered locally |
| PCE-46 | No product credential is required; forwarded identity is not an account | `tests/server/integration/test_api_app.py:395` — `forwarded.status_code == anonymous.status_code`; `tests/server/integration/test_api_app.py:396` — `forwarded.json() == anonymous.json()` | Covered |
| PCE-47 | Private access through Tailscale | No authorized host/access evidence; deployment assets alone do not prove it | EXTERNAL GAP |
| PCE-48 | Combining sequences and joined emoji count as one visual character | `tests/server/unit/test_domain_validation.py:131` — `len(title) == 400`; `tests/server/unit/test_domain_validation.py:132` — `issues_for(title=title) == ()` | Covered |
| PCE-49 | Repeated midnight uses its first occurrence | `tests/server/unit/test_clock_cutoff.py:118` — `cutoff == datetime(2026, 11, 1, 4, 0, tzinfo=UTC)`; `tests/server/unit/test_clock_cutoff.py:119` — `cutoff < datetime(2026, 11, 1, 5, 0, tzinfo=UTC)` | Covered |
| PCE-50 | Skipped Apia date uses the first instant after the skip | `tests/server/unit/test_clock_cutoff.py:154` — `cutoff == datetime(2011, 12, 30, 10, 0, tzinfo=UTC)`; `tests/server/unit/test_clock_cutoff.py:155` — `cutoff.astimezone(APIA) == datetime(2011, 12, 31, 0, 0, tzinfo=APIA)` | Covered |
| PCE-51 | Both supported date endpoints accepted as edits | `tests/server/integration/test_services_edit.py:629` — `first is not None`; `tests/server/integration/test_services_edit.py:630` — `second is not None`; `tests/server/integration/test_services_edit.py:631` — `first.deadline == date(1, 1, 1)`; `tests/server/integration/test_services_edit.py:632` — `second.deadline == date(9999, 12, 30)` | Covered |
| PCE-52 | Out-of-range edit is rejected without state change | `tests/server/integration/test_services_edit.py:644` — `result.outcome == 'rejected'`; `tests/server/integration/test_services_edit.py:645` — `result.error is not None`; `tests/server/integration/test_services_edit.py:646` — `result.error.fields == (INVALID_DEADLINE,)`; `tests/server/integration/test_services_edit.py:647` — `stored_columns(settings, task_id) == before` | Covered |

PCE-02 also has the whitespace, tabs, newline, NBSP and EM SPACE parameterized cases in `test_domain_validation.py:110`. PCE-48 also covers 201 combining/emoji titles and 5,000/5,001 observation clusters; no code-point or byte counting is substituted. PCE-19/24/25 have matching edit and pending/completed/deleted population cases in `test_services_uniqueness.py`. PCE-43 also compares a consulted rejection's HTTP 200 with its retained rejected outcome in `test_api_operations.py:221`.

**Time oracle check:** cutoff expectations are literal, spec-aligned UTC instants, not values generated by the cutoff helper. The protected Apia oracle is `2011-12-30T10:00:00Z`; repeated Havana midnight expects the earlier occurrence. The 13 parameterized fixtures cover ordinary and 23/25-hour days, missing/repeated midnight, a whole skipped date, and both supported date endpoints in UTC and positive/negative fixed offsets. This audit verified fixture/code consistency; it did not freshly download IANA sources or assert power-loss guarantees.

## Discrimination sensor

**Depth:** nine targeted behavior mutations for this data-integrity feature. This is an expanded manual sensor, not exhaustive mutation coverage of every branch.

A fresh temporary directory contained copies of all tracked and nonignored untracked working-tree files, including the initial cache files. The sensor changed only copied production files. PYTHONPATH was pinned to the scratch package root; a subprocess asserted that the imported `task_analyzer_server.__file__` resolved under that copy. A full unmutated scratch suite passed 588/588 before any mutations. Each mutation ran in a fresh Python process, then its source file was restored byte-for-byte inside the scratch. Existing tests were unchanged.

| Mutation | Production location | Injected behavior | Suite | Result |
| --- | --- | --- | --- | --- |
| M01 | `src\task-analyzer-server\task_analyzer_server\domain.py:39` | `TITLE_MAX_CLUSTERS = 200` → `TITLE_MAX_CLUSTERS = 199` | `tests/server/unit/test_domain_validation.py` | KILLED, exit 1; 4 failed, 48 passed |
| M02 | `src\task-analyzer-server\task_analyzer_server\domain.py:201` | `_GRAPHEME_CLUSTER.finditer(text)` → `text` | `tests/server/unit/test_domain_validation.py` | KILLED, exit 1; 4 failed, 48 passed |
| M03 | `src\task-analyzer-server\task_analyzer_server\domain.py:43` | `MAXIMUM_DEADLINE = date(9999, 12, 30)` → `MAXIMUM_DEADLINE = date(9999, 12, 31)` | `tests/server/unit/test_domain_validation.py` | KILLED, exit 1; 1 failed, 51 passed |
| M04 | `src\task-analyzer-server\task_analyzer_server\domain.py:92` | `return collapsed.casefold()` → `return collapsed.lower()` | `tests/server/unit/test_domain_title_key.py` | KILLED, exit 1; 1 failed, 16 passed |
| M05 | `src\task-analyzer-server\task_analyzer_server\clock.py:148` | `min(exact)` → `max(exact)` | `tests/server/unit/test_clock_cutoff.py` | KILLED, exit 1; 4 failed, 35 passed |
| M06 | `src\task-analyzer-server\task_analyzer_server\storage.py:247` | `connection.execute(COMMIT)` → `connection.execute("ROLLBACK")` | `tests/server/integration/test_services_runner.py` | KILLED, exit 1; 11 failed, 10 passed |
| M07 | `src\task-analyzer-server\task_analyzer_server\services.py:759` | `return retained.result` → `return command(connection, request)` | `tests/server/integration/test_services_runner.py` | KILLED, exit 1; 2 failed, 19 passed |
| M08 | `src\task-analyzer-server\task_analyzer_server\storage.py:295` | `return ConfiguredZone(ZoneOutcome.CONFLICTING, retained)` → `return ConfiguredZone(ZoneOutcome.ALREADY_SET, retained)` | `tests/server/integration/test_services_configuration.py` | KILLED, exit 1; 4 failed, 11 passed |
| M09 | `pyproject.toml:9` | `requires-python = ">=3.13"` → `requires-python = ">=3.12"` | `tests/server/unit/test_packaging_metadata.py` | KILLED, exit 1; 3 failed, 2 passed |

Each command used `python -m pytest <listed suite> -q`, the declared pytest gate restricted to tests of the mutated behavior. Failures were behavioral assertions or required boundary checks, not import/collection failures. **Result: 9 injected, 9 killed, 0 survived.** This does not negate the concrete coverage gaps exposed by the separate F1-F5 reproductions.

**Isolation:** immediately before and after the sensor, real `git status --porcelain` contained exactly:

```text
?? src/task-analyzer-server/task_analyzer_server/__pycache__/
?? tests/server/integration/__pycache__/
?? tests/server/unit/__pycache__/
```

The comparison was equal. The scratch was then deleted only after checking its resolved parent/name against the allocated temporary audit root. No git stash was used. Report, lesson and root Handoff edits occurred after this isolation check. The source/test tree stayed unchanged.

Raw build, baseline, provenance, and mutation logs for this run were retained under `C:/Users/Becker/AppData/Local/Temp/task-analyzer-audit-42a4a6f99c2240ecb42ce99a705caea0/`; these are temporary supporting artifacts. Reproduction scheduling, inputs, outputs and requirement evidence are recorded above so the findings do not depend on those temporary paths remaining available.

## Code quality and scope

- The approved source/module layout, Python types, and configured formatter/linter/type gates are followed. Validation, title comparison, storage transactions, services, and HTTP mapping remain separate; no extra lifecycle commands, metrics, client, accounts, or backlog capabilities were added.
- Existing tests preserve the protected input pairs and exercise stored outcomes, whole-state rejection preservation, immutable replay, restart, and uniqueness populations. Their nominal assertions are useful and the sensor confirms discrimination for its nine targets.
- Per-layer completeness is **not** established: initializer ownership races, async routing under real database contention, parser/canonicalization numeric boundaries, coherent read snapshots, and actual runtime logger configuration are missing scenarios (F1-F5).
- Existing module-level REQ/PCE annotations provide traceability; not every test has a standalone criterion annotation. No criteria or approved test meaning was changed by this audit.
- Backend-only automated checks apply here; Windows UI layout/UAT and future 1B transitions remain outside this delivery.
- README, AGENTS, and some historical spec prose still describe pre-implementation state. The reconciled Handoff and Git history establish current task completion; those historical phrases must not be treated as proof that the implementation is absent or that approval was never granted. This audit did not rewrite product inputs.

## Historical verification and lesson provenance

The preceding report at `9541255`/`aa59004` covered `127d777..5fe1955`. Its 588-test result and earlier sensor outcomes are historical evidence, not this audit's measurements. This report supersedes its statement that only external work remains.

**Historical Finding 2 / mutant M11 (resolved):** the earlier sensor lowered `pyproject.toml` from Python `>=3.13` to `>=3.9`; the original 583 tests did not detect it. Fix `5fe1955` added five packaging-metadata tests. The earlier re-verification killed both `>=3.9` and `>=3.12` variants. That is the original grounding for candidate lesson **L-001**, whose source string refers to "validation.md Finding 2 (mutant M11)". It is distinct from new finding F2 in this report. This audit's M09 independently killed `>=3.12` again.

**Historical sensor pass 1 / L-002:** the preceding report discarded an initial ten-mutation run because an editable install imported the real checkout rather than the scratch. Its rerun pinned PYTHONPATH and checked provenance. The existing candidate lesson **L-002** refers to that historical event; it is not a claim that any mutation survived in this audit. The original L-001/L-002 entries were preserved.

New grounded F1-F5 gaps are recorded only through the installed `scripts/lessons.py`, as project-local candidate lessons. No recurrence promotion or manual bookkeeping is applied. External host authorization gaps are reported as completion constraints; they do not supply a new code implementation lesson.

## Requirement disposition

No requirement is marked Verified. Existing local evidence remains useful for REQ-007/008/010/011/028/029/031, but the newly found local defects require correction and independent re-verification. REQ-003 and REQ-027 also retain their mandatory external checkpoints. `validate_state.py` must continue to fail while this report's verdict is FAIL.

The authorized audit is complete; the implementation is not ready for overall PASS. Review the five bounded fix proposals, preserve their regression expectations, and approve the applicable fix plan before changing application code.

## Open questions

- When will F1-F5's correction scope be approved for implementation and independent re-verification?
- Which installed interpreter, target-specific lock, paths, tailnet hostname and authorized device identifiers will the separately authorized Ubuntu/private-access verification use?

# Server design

Delivery 1A: [specification](spec.md). The original Design and audit revision were approved on 2026-09-13. The user approved uv, concise documentation and fixes F1-F5 on 2026-09-14. Historical detail is in Git at `8c68d6a`; shared decisions are in [STATE](../../STATE.md).

## Architecture

One FastAPI application and one Uvicorn worker serve a local SQLite database on the dedicated Ubuntu host. Tailscale Serve proxies private HTTPS to `127.0.0.1:8000`. There are no product accounts, ORM, background queue or remote database. Python 3.13 is the minimum.

Package: `src/task-analyzer-server/task_analyzer_server/`.

| Module | Responsibility |
| --- | --- |
| app.py | Injectable `create_app(settings, clock)`, zero-argument runtime factory, startup verification. |
| api.py | Parse HTTP envelopes, dispatch services, publish responses and errors. |
| contracts.py | Strict input/response models and stable validation codes; does not import domain/services. |
| domain.py | Field validation, grapheme limits and title comparison. |
| clock.py | UTC clock, product date, integer microseconds and deadline cutoff. |
| services.py | Transactions for task operations/configuration, replay, validation and reads. |
| storage.py | Connections, SQL, committed snapshots and transaction completion. |
| schema.py / schema/001_initial.sql | Explicit standalone initialization from packaged DDL. |
| settings.py / logging_config.py | Environment validation and standard-library structured logging. |

Async routes await request bodies, then offload each complete blocking service invocation to a worker thread. A connection is opened, used and closed in that same invocation. The clock is injectable; tests use real disposable SQLite databases.

## Persistence and initialization

| Table | Stored contract |
| --- | --- |
| product_configuration | Singleton key 1 and validated IANA product_time_zone. |
| tasks | UUID task_id, submitted title, derived title_key, nullable observations/deadline_date, pending/completed status, original created_at_us, nullable latest_completed_at_us, is_deleted 0/1. |
| operation_results | UUID operation_id, canonical request, terminal outcome, original HTTP status, immutable serialized result and resolved_at_us. |
| schema_version | Singleton initial schema version 1. |

Create pending, non-deleted tasks without a completion timestamp. Managed reads exclude deleted rows. 1A has no lifecycle/deletion commands; completed/deleted rows support comparison fixtures for 1B.

Two unique partial indexes enforce dated `(title_key, deadline_date)` among all non-deleted rows and undated `title_key` among non-deleted pending rows. Services check under the write transaction and exclude the edited task itself. Deleted rows never conflict; completed undated rows do not conflict.

Every connection uses `mode=rw`, explicit transaction control (`isolation_level=None`, pinned legacy autocommit), thread checking, and verified PRAGMAs: `journal_mode=DELETE`, `synchronous=EXTRA`, `foreign_keys=ON`, `busy_timeout=5000` by default. Database and journal stay on the same local filesystem.

Startup checks the existing database version and readable configuration; it never initializes or migrates. An initialized but unset product zone is allowed. The separate initializer atomically claims a new path exclusively; only that invocation can clean up its failed partial database. An existing path is refused.

Task writes use `BEGIN IMMEDIATE`; failures roll back active transactions and close connections. Do not use `executescript` inside operation transactions. A task-list read uses one read transaction for its zone and items, and samples server time once.

## Validation and time

- Title: required, nonblank, at most 200 extended grapheme clusters after trimming U+0020 edge spaces. Observations: optional, at most 5,000 clusters as supplied, including line breaks. Use regex `\X`; do not truncate or count bytes/code points.
- Comparison key: trim U+0020 edges, collapse interior U+0020 runs and Unicode-casefold. Retain accents; do not normalize compatibility characters or interior tabs/newlines. Store submitted text separately.
- Deadlines are exact ASCII `YYYY-MM-DD` calendar dates in `0001-01-01` through `9999-12-30`. Past dates are allowed. Optional fields omitted or null become absent.
- Instants are aware UTC values, stored as integer microseconds using integer/timedelta arithmetic. Serialize UTC with six fractional digits and `Z`; UUIDs use lowercase hyphenated text.
- Initial configuration validates an IANA key and retains it unchanged. The same key is safe to repeat; another key conflicts. Product date comes from server time in that zone, never the client/host display zone.
- Cutoff is the next calendar boundary in the product zone. Round-trip both fold candidates and choose the earliest valid UTC instant. If midnight is absent, bisect the forward transition to the first existing instant at or after the boundary, including after a skipped date. Check the immediately preceding microsecond; guard overflow before conversion. Do not add 24 elapsed hours or merely add an offset difference.
- Preserve the independent ordinary, Havana repeated-midnight and Apia skipped-date oracles, plus both supported date endpoints and both offset directions. Completion timestamps/emphasis remain outside 1A.

## HTTP contract

| Route | Input | Response |
| --- | --- | --- |
| GET /v1/configuration | None | ConfigurationView. |
| PUT /v1/configuration | Exactly product_time_zone string | Atomic compare-and-set ConfigurationView; no operation ledger. |
| GET /v1/tasks | None | All managed tasks, product_time_zone, server_now, product_date. No sorting/filtering/pagination guarantee. |
| POST /v1/tasks | Operation-Id UUID header and task input | 201 with durable creation result. |
| PUT /v1/tasks/{task_id} | Operation-Id and full editable task input | 200 with durable pending-edit result. |
| GET /v1/operations/{operation_id} | Original UUID | 200 with either original terminal outcome; unknown is a distinct 404. |

Task input is exactly title string, optional observations string/null and deadline string/null. Reject unknown/server-owned fields and coercion. Invalid JSON constants are envelope errors; valid numeric wrong-type values, including values beyond finite float range, remain durable field rejections. Canonicalization preserves their numeric type instead of turning them into strings.

| Model | Exact public fields |
| --- | --- |
| TaskSnapshot | task_id, title, observations, deadline, status, created_at, completed_at. Nullable observations/deadline/completed_at; no internal keys or deletion flags. |
| ConfigurationView | configured, product_time_zone, server_now, product_date. Zone/date are null before setup. |
| TaskListView | items, product_time_zone, server_now, product_date. |
| OperationResult | operation_id, outcome, original_http_status, task, error, resolved_at. Exactly one of task/error is non-null. |
| OperationError | code, fields array of {field, code}, conflicting_task_id (nullable). |
| ProtocolError | request_id, error {code, fields}, operation_id only when usable. No terminal outcome/task. |

All API responses use `Cache-Control: no-store`. A successful lookup's HTTP 200 does not mean the operation succeeded: inspect outcome. Current task state is read separately from an old operation snapshot.

| Case | HTTP / code | Retained result |
| --- | --- | --- |
| Invalid task fields | 422 TASK_VALIDATION_FAILED | Rejection; no task changes. |
| Uniqueness conflict | 409 TASK_UNIQUENESS_CONFLICT | Rejection naming conflicting_task_id; both tasks unchanged. |
| Absent/deleted edit target | 404 TASK_NOT_FOUND | Rejection; no implicit creation. |
| Completed edit target | 409 TASK_STATE_INCOMPATIBLE | Rejection; 1B adds completed-observation editing. |
| Reused operation ID with changed request | 409 OPERATION_ID_REUSED | Preserve original result. |
| Invalid envelope | 400 INVALID_OPERATION_ENVELOPE | None. |
| Unknown lookup | 404 OPERATION_RESULT_UNKNOWN | No claim of rejection or rollback. |
| Zone not configured / another zone already fixed | 409 PRODUCT_TIME_ZONE_REQUIRED / PRODUCT_TIME_ZONE_FIXED | No task result. |
| Invalid zone | 422 INVALID_TIME_ZONE | No configuration change. |
| Storage failure / unexpected defect | 503 STORAGE_UNAVAILABLE / 500 INTERNAL_ERROR | Never invent an uncommitted outcome. |

Field codes: TITLE_REQUIRED, TITLE_TOO_LONG, OBSERVATIONS_TOO_LONG, INVALID_DEADLINE, INVALID_FIELD_TYPE, UNEXPECTED_FIELD. Do not echo submitted values or framework validation objects.

## Operation recovery

1. Parse a usable envelope and build deterministic text from version, method, canonical target and parsed JSON. Object order/JSON whitespace do not matter; changed content/target does. Keep values before business normalization.
2. Acquire the write transaction before ledger/uniqueness checks.
3. Same ID/request returns the stored result without revalidation or mutation. Different content under that ID is a protocol conflict.
4. Validate new attempts. Store business rejections; store accepted task mutation and serialized success result in the same transaction. Sample original creation time when applying creation with write access held.
5. Commit before returning success/rejection. Prepare terminal serialization before storage. On unexpected failure, roll back; failed commit is never success.

Keep results indefinitely without TTL or cascading task foreign keys. A crash before commit leaves no partial pair; after commit a lost response remains consultable. An old edit replay never overwrites later state. Original rejection stays rejected even if its conflict disappears. Unknown lookup can mean work is still in flight. No pending ledger row or background worker is needed. The desktop's 15-second feedback timer is not server cancellation or a processing deadline.

## Runtime and verification

Use uv with pyproject.toml/uv.lock and an ignored local .venv; pytest/HTTPX, Ruff, strict mypy and build remain the quality tools. [README](../../../README.md#quality-checks) owns executable local commands. Package SQL in the wheel; installed tests initialize/start/restart outside the checkout. Lock resolution alone does not prove actual Ubuntu compatibility.

Runtime entry: `task_analyzer_server.app:application_factory --factory`, one Uvicorn worker on loopback, no reload. Settings: required absolute TASK_ANALYZER_DATABASE_PATH; TASK_ANALYZER_LOG_LEVEL=INFO and TASK_ANALYZER_DB_BUSY_TIMEOUT_MS=5000 defaults. The product zone is database configuration, not an environment override.

JSON-line logging covers application and Uvicorn handlers: timestamp, level, event, request_id, outcome, error_code, duration_ms; optional operation_id/task_id. Use monotonic durations, report runtime/time-data versions, correlate protocol errors with request_id, and emit task success only after commit. No titles, observations, canonical requests, bodies or secrets. Log formatting cannot decide transaction success.

[Deployment](../../../docs/architecture/deployment/server.md) owns host setup, systemd and Tailscale steps. Real-host and database changes require separate authorization. Local checks and a deployment guide do not close PCE-47 or the target-interpreter checkpoint.

## Open questions

Actual Ubuntu interpreter, host paths and private-access values remain unverified. Windows client, 1B and analysis contracts remain separate work.

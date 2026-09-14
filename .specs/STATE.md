# STATE

## Decisions

Approved product inputs remain in [Requirements](../docs/product/requirements.md) and [Scope](../docs/product/scope.md). [AGENTS.md](../AGENTS.md) owns working rules, authorization, and unresolved technical choices. Consult those sources before recording new project-level decisions; do not reproduce product definitions here.

### AD-001

- **Decision**: Use one FastAPI application with SQLite on local storage of the dedicated Ubuntu Server 26.04.1 LTS host, retaining Python 3.11+ and private Tailscale access.
- **Reason**: The user selected this architecture for the personal collection after comparing it with a separately operated PostgreSQL service.
- **Trade-off**: Accept serialized SQLite writes and local-storage coupling to avoid operating a separate database service. Database contention must be handled without weakening uniqueness, persistence, or safe operation repetition.
- **Scope**: Server features and their shared persistence/operation contracts; details are proposed in the [1A Design](features/persistent-task-creation-editing/design.md).
- **Date**: 2026-09-13.
- **Status**: active; the Python baseline named here is superseded by [AD-003](#ad-003).

### AD-002

- **Decision**: Adopt the shared server contracts of the approved 1A Design: versioned HTTP JSON request/response over `/v1`, client-supplied operation identity with an immutable result ledger written in the same SQLite transaction as its mutation, aware-UTC instants with integer microsecond storage and a persisted IANA product-zone key, explicit `BEGIN IMMEDIATE` transactions with verified PRAGMAs, native virtual environment plus systemd plus Tailscale Serve for private access, JSON-line structured logging, and pytest, HTTPX, Ruff, mypy, build, and pip-tools as the server quality stack.
- **Reason**: The user approved the detailed 1A Design on 2026-09-13. These contracts are reused by delivery 1B, deadline emphasis, productivity analysis, and the desktop client, so they belong in the project decision log rather than one feature document.
- **Trade-off**: Request/response with an operation ledger keeps the desktop responsible for repetition and refresh, and indefinite result retention trades storage for the guarantee that a late repeated attempt never becomes a new operation.
- **Scope**: Server features and their shared persistence, operation, time, logging, and quality contracts. Exact dependency versions, deployment values, and client technology remain outside this entry.
- **Date**: 2026-09-13.
- **Status**: active.

### AD-003

- **Decision**: Require Python 3.13 or later for the Task Analyzer Server, replacing the earlier 3.11 minimum.
- **Reason**: The user raised the baseline on 2026-09-13 while approving the task plan, so the server targets a current interpreter instead of the oldest one that satisfies the original requirement.
- **Trade-off**: A newer minimum narrows the set of acceptable host interpreters and must match what the selected Ubuntu Server 26.04.1 LTS target actually provides; the dependency task verifies that interpreter before locking versions.
- **Scope**: Server runtime, packaging metadata, dependency resolution, and the REQ-003/PCE-44 criteria. It supersedes only the Python baseline of [AD-001](#ad-001); every other part of that decision stays active.
- **Date**: 2026-09-13.
- **Status**: active.

## Handoff

- **Feature**: [Persistent task creation and editing](features/persistent-task-creation-editing/spec.md), delivery 1A.
- **Phase / Task**: New feature work paused by the user on 2026-09-14. The completed code audit remains **FAIL** for reproduced local defects and missing target-host evidence. Current work is to reassess the project's development process and excessive documentation/test volume before continuing implementation.
- **User priorities**: This is a personal, educational and portfolio project. Keep the implementation understandable and the development workflow proportionate; the current content volume and context-loading cost are unacceptable to the user. This priority does not silently remove approved behavior or protected test scenarios.
- **Completed**: The 31 implementation tasks remain committed, followed by the earlier validation fix and handoff at `aa59004`. This audit changes documentation and script-managed lessons only; application code and provided tests are unchanged.
- **Findings**: Concurrent initialization can delete the database created by the winning initializer; synchronous SQLite calls block the event loop in async routes; invalid JSON numbers escape as HTTP 500; and task-list reads can combine tasks with an obsolete unset product zone. Runtime logging also retains Uvicorn's plain-text handlers. See the ranked findings and proposed fix tasks in [validation.md](features/persistent-task-creation-editing/validation.md).
- **Checks**: Fresh hash-locked Python 3.13 environment: 588 tests passed, 0 failed, 0 skipped; Ruff formatting/lint, strict mypy, dependency consistency and package build passed. A disposable source copy also passed all 588 tests. Nine behavior mutations were killed, with no survivors. Import provenance was pinned to that copy and real-tree porcelain matched before and after the sensor.
- **Verification**: Audit scope `127d777..aa59004`, including the pre-existing untracked cache directories. Both the main reviewer and independent Verifier reproduced all four functional findings using disposable databases. Passing existing tests does not close these missing scenarios. No requirement is promoted to Verified.
- **Next step**: Explain the causes of the excessive volume, then agree on a concise simplification scope for repository instructions, documentation, local setup and test organization. Keep the audit findings visible in that scope. Do not start new features or execute a broad rewrite or test deletion from this pause instruction.
- **Deployment checkpoint**: PCE-47 and PCE-44's actual Ubuntu interpreter check remain pending. No host was contacted, deployment performed, or real database modified. Target values and deployment/database authorization remain required.
- **Authorization**: This session authorizes the audit and its local evidence artifacts. Existing implementation authorization remains recorded in the approved plan; no push, merge, deployment or destructive action is authorized.
- **Uncommitted files**: Audit report, this Handoff and script-managed lesson updates; the pre-existing untracked `__pycache__/` directories remain. Reconcile Git on resume.
- **Lessons**: New audit signals are recorded through the installed `lessons.py`; consult the canonical store for current candidate status. No lesson is promoted merely by recurring within this same feature.
- **Branch**: `docs/1a-code-audit`, created from `feat/persistent-task-creation-editing` at `aa59004`. Not pushed or merged.

## Open questions

No unresolved TLC integration decisions remain. [AGENTS.md](../AGENTS.md#open-questions) owns future MVP technical decisions; the product documents retain their own questions. Reconcile this handoff against Git before resuming work.

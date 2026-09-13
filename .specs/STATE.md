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

- **Feature**: [Persistent task creation and editing](features/persistent-task-creation-editing/spec.md), delivery 1A of the server lifecycle group.
- **Phase / Task**: Tasks drafted and revised; awaiting user approval. No implementation has started and no task is in progress.
- **Completed**: Approved 1A specification; approved detailed Design (2026-09-13) recorded in [AD-002](#ad-002); formal `tasks.md` with 31 atomic tasks in 9 phases. On 2026-09-13 the user also adopted TLC's commit standard in [AGENTS.md](../AGENTS.md#branches-and-authorization), confirmed that no MCP server or additional skill is needed, and raised the runtime baseline to Python 3.13+ ([AD-003](#ad-003)), propagated to REQ-003, PCE-44, the design, and T1/T2.
- **In-progress** (file:line): `features/persistent-task-creation-editing/tasks.md:19` marks the task plan as Draft awaiting approval. `python .ai/skills/tlc-spec-driven/scripts/validate_tasks.py` reports 0 errors and 4 expected `Tests: none` warnings for the packaging and deployment-asset tasks.
- **Next step**: Obtain task approval, then answer the sub-agent offer at Execute (31 tasks pack into more than one batch) before implementing T1. Each completed task now ends in its own atomic Conventional Commit.
- **Deployment target**: The user's own Ubuntu server, confirmed 2026-09-13. No disposable validation host is used, so PCE-46/PCE-47 evidence and every install, service, Tailscale, and database-initialization step wait for step-level authorization and the host values the user still has to supply.
- **Blockers**: None for task approval. Exact dependency versions are resolved in T2 against the interpreter the Ubuntu target provides; the private-access checks in PCE-46/47 need an explicitly authorized environment and are not performed by any task.
- **Uncommitted files**: `AGENTS.md`, `README.md`, `docs/product/requirements.md`, and `.specs/STATE.md` modified; `spec.md`, `design.md`, and `tasks.md` are present in the untracked feature directory. No commit has been made for this work; the new commit standard applies to task execution.
- **Branch**: `docs/persistent-task-creation-editing`. Git history ends at `2fafba2`; reconcile Git again on resume rather than relying on earlier conversational snapshots.

## Open questions

No unresolved TLC integration decisions remain. [AGENTS.md](../AGENTS.md#open-questions) owns future MVP technical decisions; the product documents retain their own questions. Reconcile this handoff against Git before resuming work.

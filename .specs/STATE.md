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
- **Phase / Task**: Documentation audit corrections complete. Behavioral clarifications are approved; the revised Design and formal Tasks await review/approval. No application task has started.
- **Completed**: D1 (`bb0cd44`) records approved TIME-02/03, with 52 PCE criteria and all original scenario examples preserved. D2 (the commit carrying this snapshot) corrects bootstrap gates, one-way input/domain dependencies, independent initialization, the HTTP foundation, exact request correlation, installed-wheel verification and stale project status.
- **Plan**: 31 unchecked implementation tasks in 9 phases; T11 precedes T7. T22 delivers the tested HTTP boundary across app.py/api.py; T27 verifies the installed distribution. Four proposed whole-phase batches are documented; worker delegation still requires the Execute-time offer and user choice.
- **Checks**: validate_spec: 0 errors/0 warnings. validate_tasks: 0 errors/5 reviewed warnings (four none-test packaging/assets and T22's intentional two-file boundary). Semantic checks preserved every original product acceptance scenario, found exactly the approved PCE-08/09/50 wording changes plus PCE-51/52, verified 31 ordered task IDs, 176 local links/anchors and final Open questions headings. git diff --check passed. Application tests have not run.
- **Next step**: Review the corrected Design and approve the task plan before any application implementation. Earlier AD-003 wording about task-plan approval records the runtime decision; it does not approve the current revised tasks.
- **Deployment checkpoint**: The user's own Ubuntu server still requires supplied host values and explicit deployment/database authorization. Confirm its interpreter before creating/validating its target-specific lock; local Python 3.13 locks are not target evidence. Overall feature PASS/Verified remains blocked until the required runtime and private-access checks pass.
- **Authorization**: Documentation and local commits only for this round. No push, merge, application implementation, deployment or real database changes.
- **Uncommitted files**: The D2 documentation changes are included in the commit carrying this snapshot; reconcile Git on resume.
- **Branch**: `docs/1a-audit-corrections`, based on merged `main` at `c052f35`.

## Open questions

No unresolved TLC integration decisions remain. [AGENTS.md](../AGENTS.md#open-questions) owns future MVP technical decisions; the product documents retain their own questions. Reconcile this handoff against Git before resuming work.

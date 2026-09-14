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
- **Status**: active; dependency locking with pip-tools is superseded by AD-004.

### AD-003

- **Decision**: Require Python 3.13 or later for the Task Analyzer Server, replacing the earlier 3.11 minimum.
- **Reason**: The user raised the baseline on 2026-09-13 while approving the task plan, so the server targets a current interpreter instead of the oldest one that satisfies the original requirement.
- **Trade-off**: A newer minimum narrows the set of acceptable host interpreters and must match what the selected Ubuntu Server 26.04.1 LTS target actually provides; the dependency task verifies that interpreter before locking versions.
- **Scope**: Server runtime, packaging metadata, dependency resolution, and the REQ-003/PCE-44 criteria. It supersedes only the Python baseline of [AD-001](#ad-001); every other part of that decision stays active.
- **Date**: 2026-09-13.
- **Status**: active.

### AD-004

- **Decision**: Use lightweight SDD inspired by TLC and uv-managed dependencies/environments. Remove mandatory TLC automation, test-count quotas and blanket verbose docstrings.
- **Reason**: The user approved simplification after the first delivery exposed disproportionate content and context-loading cost for a personal learning/portfolio project.
- **Trade-off**: Keep behavior-based specifications, tests and review, while replacing generated process artifacts with concise guidance and Git history. The bundled TLC remains optional study material.
- **Scope**: Repository workflow and dependency management; supersedes pip-tools in AD-002, preserving its server contracts and other tools.
- **Date**: 2026-09-14.
- **Status**: active.

## Handoff

- **Work**: Approved project simplification is complete locally; new features remain paused pending review. See [maintenance](../docs/maintenance.md) for results.
- **Branch**: `fix/project-simplification`, based on the preserved audit at `8c68d6a`.
- **Next step**: Review the simplification report and decide when to resume feature planning under lightweight SDD.
- **Result**: uv and `.venv` are established; F1-F5 are fixed; active documentation, source commentary and duplicate tests are reduced. The final 393-case suite and quality/build checks pass.
- **Authorization**: Local maintenance implementation and commits. No push, merge, deployment or real database changes.
- **Existing local change**: `.specs/features/.gitkeep` was already deleted before maintenance; preserve it separately from maintenance commits.
- **External checks**: Actual Ubuntu interpreter/lock and Tailscale access remain pending; local maintenance completion does not claim deployment verification.

## Open questions

No unresolved TLC integration decisions remain. [AGENTS.md](../AGENTS.md#open-questions) owns future MVP technical decisions; the product documents retain their own questions. Reconcile this handoff against Git before resuming work.

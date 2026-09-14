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
- **Phase / Task**: Execute complete locally. All 31 implementation tasks are committed and the independent Verifier has reported. The feature is **not** complete: its verdict is FAIL on external evidence alone.
- **Completed**: 31 of 31 tasks, one atomic commit each, `9d4e1c6` through `85afe10`. The server package holds settings, logging, schema plus its initializer, contracts, domain, clock, storage, services, and the composed HTTP boundary with all six `/v1` routes. `docs/architecture/deployment/` holds the systemd asset and the deployment guide. Fix commit `5fe1955` closed the one local Verifier finding; `9541255` records the report.
- **Plan**: executed as four sequential whole-phase batches, as the user chose on 2026-09-13. The batch covering T22-T31 was interrupted by a session limit after T28; T29's suite was already written and passing, and T29 through T31 were finished in the main session. T11 preceded T7 as planned.
- **Checks**: 588 tests pass, 0 failed, 0 skipped. All five gates green at `5fe1955`: ruff format, ruff check, mypy --strict, pytest, pip check. validate_tasks: 0 errors/5 reviewed warnings. validate_state: **exit 1**, correctly, because the verdict is FAIL. Discrimination sensor: 12 mutations across two passes, 12 killed, 0 survived. A first sensor pass falsely reported all mutants surviving because the editable install resolved imports to the real checkout; it was re-run with `PYTHONPATH` pinned to the scratch and a provenance guard.
- **Verification**: [validation.md](features/persistent-task-creation-editing/validation.md), diff range `127d777..5fe1955`. 51 of 52 criteria hold within the locally verifiable scope, with 0 spec-precision gaps. PCE-47 is UNMET and PCE-44's target-interpreter half is UNMET; both need the authorized host session.
- **Next step**: no local work remains for 1A and no fix task is open. Either obtain authorization for the deployment session that closes PCE-47 and the target-interpreter check, or begin the next feature's Specify. Merging this branch also needs authorization.
- **Deployment checkpoint**: The user's own Ubuntu server still requires supplied host values and explicit deployment/database authorization. Confirm its interpreter before creating/validating its target-specific lock; local Python 3.13 locks are not target evidence. Overall feature PASS/Verified remains blocked until the required runtime and private-access checks pass. No requirement is marked Verified.
- **Authorization**: Local implementation and per-task local commits under the approved plan. No push, merge, deployment, real-host configuration or real database changes.
- **Uncommitted files**: none beyond untracked `__pycache__/` directories, which are not yet covered by `.gitignore`. The lessons store and this snapshot are in the commit carrying them; reconcile Git on resume.
- **Lessons**: two candidates recorded from grounded sensor signals, `L-001` (pin approved configuration values with a failing test) and `L-002` (pin `PYTHONPATH` to the scratch when mutating). Both stay candidates until a second feature corroborates them; neither is guidance yet.
- **Branch**: `feat/persistent-task-creation-editing`, based on `docs/1a-audit-corrections` at `127d777`. Not pushed and not merged.

## Open questions

No unresolved TLC integration decisions remain. [AGENTS.md](../AGENTS.md#open-questions) owns future MVP technical decisions; the product documents retain their own questions. Reconcile this handoff against Git before resuming work.

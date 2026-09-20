# Server design delta

Delivery 1B: [specification](spec.md). This document adds lifecycle commands to the approved [1A design](../persistent-task-creation-editing/design.md); all shared architecture, time, transaction, logging, validation, operation-recovery and deployment decisions remain unchanged.

## HTTP contract

All commands require a usable `Operation-Id` UUID header, use the existing operation envelope and return `OperationResult`. `GET /v1/operations/{operation_id}` remains the source for recovering any original result. The successful deletion result carries the task's final pre-deletion snapshot, so a lost response is distinguishable from an absent task while later managed reads exclude it.

| Route | Exact JSON input | Successful result |
| --- | --- | --- |
| `POST /v1/tasks/{task_id}/completion` | `{}` | Completed task snapshot; HTTP 200. |
| `PUT /v1/tasks/{task_id}/observations` | `{"observations": string or null}` | Completed task snapshot; HTTP 200. |
| `POST /v1/tasks/{task_id}/reopening` | `{}` | Pending task snapshot; HTTP 200. |
| `DELETE /v1/tasks/{task_id}` | `{}` | Final pre-deletion task snapshot; HTTP 200. |

The empty-object commands reject every other JSON shape or field as the durable `TASK_VALIDATION_FAILED` result, with the existing `INVALID_FIELD_TYPE` or `UNEXPECTED_FIELD` field issues. The completed-observation command accepts exactly its `observations` member; missing, non-string/non-null or extra fields are rejected using the same stable validation model. It applies the 1A observation grapheme limit without title or deadline validation because neither can change through this command.

The existing response and error shapes are unchanged. New attempts against unavailable tasks return durable `404 TASK_NOT_FOUND`; attempts against an incompatible managed state return durable `409 TASK_STATE_INCOMPATIBLE`. Reopening may return the existing durable `409 TASK_UNIQUENESS_CONFLICT` result with `conflicting_task_id`. Envelope failures and changed reuse of an operation ID remain non-terminal protocol errors, exactly as in 1A.

## State changes

All commands require configured product time, acquire the existing `BEGIN IMMEDIATE` transaction, check the operation ledger before validation or state inspection, and serialize/write their terminal result in the same transaction as an accepted mutation.

| Command | Required state | Stored mutation | Preserved fields |
| --- | --- | --- | --- |
| Complete | pending | Set `status` to `completed`; sample the server clock once and set `latest_completed_at_us` to that instant. | Identity, title, observations, deadline, `created_at_us`. |
| Edit completed observations | completed | Replace only `observations`. | Identity, title, deadline, status, `created_at_us`, `latest_completed_at_us`. |
| Reopen | completed | Set `status` to `pending` and clear `latest_completed_at_us`. | Identity, title, observations, deadline, `created_at_us`. |
| Delete | pending or completed | Set `is_deleted` to `1`; read the final snapshot before the flag makes it unmanaged. | Stored row and its historical fields; it is excluded from managed reads and conflicts. |

Before reopening, calculate the same title key and check the resulting state with the 1A partial-index rules, excluding the target task itself. The existing indexes already encode the required dated and undated uniqueness populations, including exclusion of deleted rows and completed undated rows. Completion and deletion need no new index or schema change: their updates make the existing indexes enforce the resulting population.

No migration is introduced. The 1A schema already has `status`, `latest_completed_at_us` and `is_deleted`; database initialization remains explicit and startup still refuses to initialize or migrate a database.

## Implementation and verification

Add strict command-input contracts, API handlers and service/storage operations following the 1A `create_task`/`edit_task` path. Use targeted storage helpers for each mutation rather than a generic state-update abstraction. Extend canonical operation identity with the exact method, normalized target and parsed JSON already used by 1A, so a different command, task, or body under a reused ID is rejected without replacing its stored result.

Test through service and HTTP boundaries against new disposable SQLite paths. Cover each accepted transition, every incompatible/absent/deleted rejection, observation boundaries, conflict on reopening, deletion's uniqueness effect, same-request replay, changed-ID reuse, restart recovery, rollback behavior, and concurrent incompatible lifecycle commands. Preserve all 1A regressions and run the README quality checks after implementation.

A dated collision cannot survive to be found when a task reopens, because the dated index is unique across both statuses. The reopening check stays as the backstop that would report it, and the tests prove the dated rule still holds across the transition.

Explicit regression scenarios:

- Complete a task, reopen it, delete it, then repeat the original completion request with its original operation ID. Return exactly the stored completion result without changing or recreating the task; managed reads must still exclude it.
- For concurrent commands against the same eligible task, with no other mutations and both attempts allowed to acquire the transaction: two completions with different operation IDs produce one HTTP 200 and one durable `409 TASK_STATE_INCOMPATIBLE`; two deletions with different operation IDs produce one HTTP 200 and one durable `404 TASK_NOT_FOUND`. Two identical attempts with the same operation ID return the same successful result and perform only one mutation.

## Open questions

None. Windows interaction, deletion-confirmation wording, deadline emphasis and productivity analysis remain outside delivery 1B.

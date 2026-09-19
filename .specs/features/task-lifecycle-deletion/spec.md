# Task lifecycle and deletion

Delivery 1B. This specification extends [delivery 1A](../persistent-task-creation-editing/spec.md) with the remaining server-side task lifecycle. Product inputs are [requirements](../../../docs/product/requirements.md) and [scope](../../../docs/product/scope.md).

## Scope

Allow the server to complete tasks, edit observations on completed tasks, reopen tasks and delete pending or completed tasks. Preserve task identity, original creation time, persistence and operation-result recovery from 1A.

The desktop owns buttons, unsaved form behavior, progress, Retry sequencing and deletion confirmation. Deadline emphasis, productivity calculations and their presentation remain separate features. This delivery stores the lifecycle state those features will consume; it does not calculate their results.

## Acceptance criteria

TLD identifiers supplement the original REQ identifiers; they do not replace them.

### Complete a pending task

1. WHEN a completion is applied to a pending task THEN the server SHALL change that task's status to completed. **TLD-01; REQ-008.**
2. WHEN a completion is applied THEN the server SHALL record the latest completion time from the server clock at application of that operation. **TLD-02; REQ-028.**
3. WHEN a task is completed THEN the server SHALL preserve its identity, title, observations, deadline and original creation time. **TLD-03; REQ-008, REQ-028.**
4. WHEN an undated task is completed THEN the server SHALL exclude it from conflicts with undated pending tasks, allowing its equivalent title to be used by a new undated pending task. **TLD-04; REQ-029.**
5. WHEN a dated task is completed THEN it SHALL continue to conflict with another task having an equivalent title and the same deadline date. **TLD-05; REQ-029.**
6. IF a new completion targets a task that is already completed THEN the server SHALL reject the operation without changing task state or timestamps. **TLD-06; REQ-008, REQ-028, REQ-031.**
7. IF a completion targets an absent or deleted task THEN the server SHALL reject the operation without creating or restoring a task. **TLD-07; REQ-008.**

### Edit observations on a completed task

1. WHEN valid observations are applied to a completed task THEN the server SHALL persist them without reopening the task. **TLD-08; REQ-009, REQ-010.**
2. WHEN observations are cleared from a completed task THEN the server SHALL persist their absence. **TLD-09; REQ-007, REQ-009.**
3. WHEN completed-task observations contain line breaks or exactly 5,000 user-perceived characters THEN the server SHALL retain and accept them under the 1A text rules. **TLD-10; REQ-007, REQ-009.**
4. IF completed-task observations exceed 5,000 user-perceived characters or have an invalid type THEN the server SHALL reject the operation without changing the task. **TLD-11; REQ-007, REQ-008, REQ-009.**
5. WHEN completed-task observations are edited THEN the server SHALL preserve identity, title, deadline, status, original creation time and latest completion time. **TLD-12; REQ-009, REQ-028.**
6. IF a command attempts to change the title or deadline of a completed task without first reopening it THEN the server SHALL reject the change without modifying the task. **TLD-13; REQ-008, REQ-009.**
7. IF completed-observation editing targets a pending, absent or deleted task THEN the server SHALL reject the operation without changing task state. **TLD-14; REQ-008, REQ-009.**

### Reopen a completed task

1. WHEN a valid reopening is applied to a completed task THEN the server SHALL change that task's status to pending. **TLD-15; REQ-008.**
2. WHEN a task is reopened THEN the server SHALL clear its latest completion time while preserving its identity, content and original creation time. **TLD-16; REQ-025, REQ-028.**
3. BEFORE applying a reopening, the server SHALL validate the resulting pending state under the 1A uniqueness rules without comparing the task against itself. **TLD-17; REQ-029.**
4. IF reopening an undated completed task conflicts with another undated pending task having an equivalent title THEN the server SHALL reject the reopening and identify that conflicting task. **TLD-18; REQ-029, REQ-031.**
5. IF reopening a dated completed task conflicts with another non-deleted task having an equivalent title and the same deadline THEN the server SHALL reject the reopening and identify that conflicting task. **TLD-19; REQ-029, REQ-031.**
6. IF reopening is rejected THEN the target and conflicting task SHALL remain unchanged, including their statuses and timestamps. **TLD-20; REQ-008, REQ-025, REQ-029.**
7. IF a new reopening targets a pending task THEN the server SHALL reject the operation without changing task state or timestamps. **TLD-21; REQ-008, REQ-028, REQ-031.**
8. IF reopening targets an absent or deleted task THEN the server SHALL reject the operation without creating or restoring a task. **TLD-22; REQ-008.**
9. WHEN a reopened task is completed again THEN the server SHALL preserve its original creation time and replace the cleared completion time with the new server completion time. **TLD-23; REQ-025, REQ-028.**

### Delete a managed task

1. WHEN deletion is applied to a pending or completed task THEN the server SHALL remove it from the managed task collection. **TLD-24; REQ-008, REQ-010, REQ-030.**
2. WHEN a task is deleted THEN it SHALL no longer participate in uniqueness comparisons. **TLD-25; REQ-029.**
3. WHEN a task is deleted THEN later completion, editing and reopening commands SHALL treat it as unavailable and SHALL NOT restore it. **TLD-26; REQ-008, REQ-030.**
4. IF deletion targets an absent or already deleted task THEN the server SHALL reject the new operation without changing persisted state. **TLD-27; REQ-008, REQ-031.**
### Persist and recover every lifecycle operation

1. The server SHALL confirm completion, completed-observation editing, reopening or deletion as successful only after the task change and operation result are persisted together. **TLD-28; REQ-010, REQ-031.**
2. WHEN the server restarts after confirming a lifecycle operation THEN the resulting task state and operation result SHALL remain available. **TLD-29; REQ-010, REQ-031.**
3. WHEN the same lifecycle operation attempt is repeated THEN the server SHALL return its original result without applying the transition or edit again. **TLD-30; REQ-031.**
4. WHEN a lifecycle operation response is lost after persistence THEN result consultation SHALL return its original success or rejection. **TLD-31; REQ-010, REQ-031.**
5. IF an operation identity is reused for different content, command or target THEN the server SHALL preserve the original result and reject the reuse. **TLD-32; REQ-031.**
6. WHEN distinct lifecycle operations overlap THEN every accepted result SHALL correspond to a valid serialized state, with no duplicated transition or uniqueness violation. **TLD-33; REQ-008, REQ-029, REQ-031.**
7. IF persistence fails before commit THEN the server SHALL NOT report a successful operation or retain a partial task/result pair. **TLD-34; REQ-010, REQ-031.**

## Required examples and edge cases

| Case | Expected evidence |
| --- | --- |
| Complete and repeat | One completion timestamp and one state transition; repetition returns the original snapshot. |
| Complete after an earlier reopen | Original creation time remains; latest completion time replaces the cleared prior value. |
| Undated completion | Completing `Read notes` permits a new undated pending ` READ  NOTES `. |
| Dated completion | Completing a dated `Read notes` still blocks an equivalent task on the same date. |
| Completed observations | Multiline text and the 5,000/5,001 boundary preserve the completion timestamp on acceptance or rejection. |
| Reopening conflict | An undated completed task cannot reopen while an equivalent undated pending task exists; both remain unchanged. |
| Reopening after conflict removal | After the conflicting task is deleted, a new reopening operation can succeed. The earlier rejected operation remains rejected. |
| Delete and reuse | A deleted task disappears from managed reads and no longer blocks an otherwise equivalent new task. |
| Lost response and restart | Every lifecycle command retains one consultable result and exactly one committed effect. |
| Concurrent incompatible commands | Outcomes reflect a valid order; for example, one of simultaneous Complete/Reopen attempts may become incompatible after the other commits. |

## Verification boundary

Tests SHALL exercise behavior through the service or HTTP boundary and use disposable SQLite databases. Add direct storage tests only for guarantees not observable at those boundaries. Preserve 1A regressions and reuse its operation, time, validation, logging and transaction contracts.

This delivery establishes state needed by deadline emphasis and productivity metrics. It does not verify metric inclusion, chart behavior, urgency labels, desktop confirmation text or Windows interaction.

## Open questions

None. The [Design](design.md) settled the HTTP commands, their exact bodies and the final snapshot a successful deletion returns, all on the 1A operation envelope and stable error model.

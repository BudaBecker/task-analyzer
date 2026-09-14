# MVP requirements

This document defines product behavior and acceptance scenarios for the [MVP scope](scope.md). Requirement IDs identify the inputs for future specifications and tests. The scenarios below are documentation, not executed tests.

The Task Analyzer Server owns business rules, persistence, and calculations. The Desktop App collects input and presents server results. [User flows](user-flows.md) describes interaction sequences, and [Domain vocabulary](domain.md) defines shared terms.

## Platform and access

| ID | Requirement | Acceptance scenario |
| --- | --- | --- |
| REQ-001 | Provide a Windows 11 Desktop App for personal task management and presentation of server-derived deadline emphasis and metrics. Windows 11 version 25H2 is the reference test environment. | The user manages personal tasks and reviews server results through the desktop in the Windows validation range defined by REQ-035. |
| REQ-003 | Run the Task Analyzer Server on a dedicated, self-hosted server using Python 3.13 or later. | The deployment design supports dedicated self-hosting and the minimum Python version. |
| REQ-027 | Serve one person's task collection without product accounts or authentication. Access to the dedicated server is private through Tailscale. | The user opens the desktop and accesses the personal task collection through the private connection without a product sign-in flow. |

## Tasks and server persistence

| ID | Requirement | Acceptance scenario |
| --- | --- | --- |
| REQ-007 | A task has a required title of at most 200 characters after trimming leading/trailing spaces, optional description/observations of at most 5,000 characters with line breaks allowed, an optional calendar-date deadline, and pending/completed status. Reject empty or whitespace-only titles. Past deadlines within the supported range are allowed. Deadline dates range from `0001-01-01` through `9999-12-30`, inclusive; reject dates outside that range. New tasks are pending. | A title-only task is accepted as pending. The server accepts a 200-character title and 5,000-character observations, rejects 201 and 5,001 characters respectively, and rejects a blank title. A valid past deadline is accepted. |
| REQ-008 | Allow creation, editing, completion, reopening, and deletion through the desktop. The server applies lifecycle rules and rejects changes that violate task validation or uniqueness. | A valid pending task can be edited, completed, and reopened. A rejected change leaves the task's persisted state unchanged. |
| REQ-009 | Allow description/observation edits on completed tasks without reopening, preserving completion time. Require reopening before changing their title or deadline. | Editing a completed task's observations leaves its completion measurements unchanged; changing its deadline requires a successful reopening first. |
| REQ-010 | Persist task data and lifecycle changes in the server. Changes confirmed as persisted survive closing/reopening the desktop and restarting the server. | After a successful save, restarting either component retains the task change. Desktop confirmation follows the operation-outcome rules in REQ-031. |

For REQ-007, character limits count user-perceived characters, not bytes or Unicode code points. A letter with combining marks and a combined emoji each count as one user-perceived character. Title limits still apply after trimming leading/trailing spaces; the existing 200/201 and 5,000/5,001 acceptance cases remain unchanged.

## Time and deadlines

| ID | Requirement | Acceptance scenario |
| --- | --- | --- |
| REQ-028 | The server uses its clock to record original creation time and each completion time when applying the corresponding operation. Obtain the product time zone from the desktop during initial configuration and retain it in the server. The zone remains fixed in the MVP. Use server time in that zone to determine the current product date. | Changing the desktop's clock or time zone after initial configuration does not change server timestamps, deadline interpretation, or historical calculations. Restarting the server retains the configured zone. |
| REQ-011 | Interpret a deadline as a calendar date whose cutoff is midnight immediately after that date in the product time zone. A pending task becomes overdue at the cutoff. A completion at or after the cutoff is late. | A September 14 deadline remains valid throughout September 14. At September 15, 00:00 in the product time zone, a pending task is overdue and a completion is late. |

For REQ-011, if midnight immediately after the deadline date occurs twice because of a time-zone transition, use its first occurrence. If that midnight does not exist, use the first valid instant at or after that nominal calendar boundary. If the entire following date is skipped, use the first instant after the skipped date. For example, a `2011-12-29` deadline in `Pacific/Apia` expires at `2011-12-31T00:00:00+14:00` (`2011-12-30T10:00:00Z`). These exceptional cases do not change the ordinary September 14/15 acceptance scenario.

The user approved the skipped-date clarification and the inclusive `0001-01-01` through `9999-12-30` deadline range during the 1A audit correction. Reject `9999-12-31`; the range leaves a representable next-day cutoff under the chosen server time representation. Preserve the original valid-past-date and invalid-calendar-date scenarios and add explicit range-boundary scenarios.

## Task uniqueness

| ID | Requirement | Acceptance scenario |
| --- | --- | --- |
| REQ-029 | The server validates the resulting task state for uniqueness on creation, editing, and reopening. Compare titles without case differences or extra spaces, preserving accent differences. Apply the deadline/status rules below to different tasks; do not compare a task against itself. Deleted tasks do not participate. Reject a conflicting operation without changing either task and identify the conflict to the user. | A conflicting creation or edit is rejected. Reopening a completed task without a deadline is rejected if an equivalent pending task without a deadline already exists; the first task stays completed and the existing pending task is unchanged. |

For title comparison, trim leading/trailing spaces and treat runs of internal spaces as one space. For example, `Read notes` and ` READ  NOTES ` are equivalent, while `Review résumé` and `Review resume` are different. This comparison rule does not make a title the task's identity.

| Resulting task | Conflicting existing task |
| --- | --- |
| Has a deadline, pending or completed | A pending or completed task with an equivalent title and the same deadline date. |
| Has no deadline and is pending | A pending task with an equivalent title and no deadline. |
| Has no deadline and is completed | None: completed tasks without deadlines do not participate in uniqueness checks. |

Acceptance examples for REQ-029:

- Two tasks with equivalent titles and different deadline dates can coexist.
- An undated task and a dated task with equivalent titles can coexist.
- Completing an undated task allows another pending undated task with the same title to be created.
- Completing a dated task does not free its title/date combination.
- Deleting a task removes it from uniqueness checks.
- Editing an existing task without changing its uniqueness combination does not conflict with that same task.

## Commands, operation outcomes, and temporary input

| ID | Requirement | Acceptance scenario |
| --- | --- | --- |
| REQ-030 | Creation and text/deadline edits require the user to select **Save**. **Complete** and **Reopen** submit their operations directly. **Delete** requires explicit confirmation identifying the task title and warning that deletion is permanent; confirmation immediately submits deletion without a separate save action. | Editing a title does not persist it before Save. Confirming deletion sends the operation immediately; cancelling confirmation sends no deletion. A successful deletion removes the task from the managed list and metrics. |
| REQ-031 | Show an operation as successful only after server confirmation of persistence. While awaiting a response, show progress and prevent repeated submission of that operation. Distinguish server rejection from an unknown result. If no confirmation arrives within 15 seconds, show **Result not confirmed**. Retry must first consult the original operation's result; the server must recognize repeated attempts and prevent duplicate application. | A persisted operation whose response is lost is shown as unconfirmed after 15 seconds. Retrying obtains its result without creating another task or applying the transition again. A uniqueness rejection is a validation failure, not a successful retry of a different operation. |
| REQ-032 | If the server is unavailable at startup, show the connection problem and **Retry**, keeping task operations unavailable until communication is established. Preserve form input in memory during failures while its window remains open. Closing a form or the app with unsent edits requires a warning about losing the input and explicit discard confirmation, with the option to cancel closing. Do not persist local drafts. On restart, load server-persisted state without automatically resending earlier changes. | A failed save leaves the typed input available in the open form. Cancelling a close warning preserves it; confirming discard closes the form without submitting those edits. Restarting the desktop restores only server-persisted data and submits no previous draft automatically. |

A client timeout does not establish that the server rejected, cancelled, or rolled back an operation. Repeating the same attempt and creating a different task are separate cases: REQ-031 protects against applying one operation twice; REQ-029 rejects different tasks that violate uniqueness. The technical contract for identifying attempts and consulting their results belongs in the relevant design.

## Visual deadline emphasis and refresh

| ID | Requirement | Acceptance scenario |
| --- | --- | --- |
| REQ-026 | The server derives emphasis for pending tasks using the product date and deadline: **no deadline** when absent; **normal** when more than 3 calendar days remain; **due in 1-3 days** when 1, 2, or 3 calendar days remain; **due today** on the deadline date; **overdue** at or after its cutoff. Reevaluate after relevant edits or reopening. Completed tasks have a neutral **Completed** presentation, with their deadline date visible when present and no deadline urgency emphasis. | On September 11, pending tasks without a deadline, due September 15, due September 12-14, due September 11, and due September 10 receive the corresponding states. Completing an overdue task removes urgency emphasis while retaining its deadline and late completion for analysis. |
| REQ-034 | Refresh task deadline emphasis and metrics after each confirmed operation, when opening or returning to the relevant view, and within 60 seconds after the date changes in the product time zone while server communication is available. Obtain calculated results from the server. | With the view open and communication available, a task due today becomes visibly overdue within 60 seconds of its cutoff. Returning to the metrics view requests current server results. A rejected reopening leaves the persisted task status and its contribution to metrics unchanged. |

## Productivity metrics

| ID | Requirement | Acceptance scenario |
| --- | --- | --- |
| REQ-021 | The server calculates total, pending, and completed task counts, average completion duration, average deadline-window percentage, and overdue rate across all task history. Present overall values without priority grouping. Total count equals pending plus completed, excluding deleted tasks. | Two pending and three completed tasks produce total 5, pending 2, and completed 3. Adding a deleted task does not change those values. |
| REQ-022 | Measure completion duration as completion time minus original creation time. Average durations across completed, non-deleted tasks. | Tasks completed after 2 and 4 hours produce an average completion duration of 3 hours. Pending tasks do not enter the average. |
| REQ-023 | Calculate each completed task's deadline-window percentage using the formula below. Show N/A without a deadline or if its cutoff is at or before creation. Average the valid percentages of completed, non-deleted tasks. Do not cap percentages at 100%. | Completion halfway through a valid window yields 50%; completion after 1.5 times that window yields 150%. Those two percentages average to 100%. Absent or invalid windows are excluded from the average. |
| REQ-024 | Calculate overdue rate only from completed, non-deleted tasks with a deadline. The numerator counts those completed at or after their deadline cutoff; the denominator counts all completed, non-deleted tasks with a deadline, including those completed before a future cutoff. Exclude all pending tasks, including currently overdue ones. | One late completion among three completed tasks with deadlines produces 33.3% when displayed. Adding pending overdue tasks or completed tasks without deadlines does not change that rate. Completion exactly at the cutoff is late. |
| REQ-025 | Exclude deleted tasks from every metric. A successful reopening removes a task from completed counts, duration/percentage averages, and overdue rate until it is completed again; it contributes to pending counts instead. On completion again, use original creation time and latest completion time. | Successfully reopening a task removes its previous completion measurements from the indicators. Completing it again measures from its original creation time to the new completion time. A rejected reopening preserves the existing measurements. |

The deadline-window percentage is:

```text
[(completion time - original creation time) / (deadline cutoff - original creation time)] * 100
```

The overdue rate is:

```text
[late completed tasks with deadlines / all completed tasks with deadlines] * 100
```

Both formulas exclude deleted tasks. The deadline-window percentage expresses how much of the available window was consumed, not progress on the task. For a valid individual task window, exactly 100% means completion at the cutoff and is late; values above 100% are also late. Classify completion from timestamps, not from a rounded display value or an aggregate average.

### Metric presentation

| ID | Requirement | Acceptance scenario |
| --- | --- | --- |
| REQ-033 | Provide a dedicated metrics area with the task counts and three aggregate completion indicators, a pending/completed task chart, and an on-time/late completion chart using REQ-024's eligible population. Hovering over chart elements shows values and explanations. Apply the display rules below without changing full-precision calculations. | The dashboard shows the overall indicators and the two charts. Hovering reveals their values and meaning. A pending overdue task appears in pending counts but does not enter the on-time/late completion chart. |

| Value | Display rule |
| --- | --- |
| Task counts | Whole numbers; an empty category displays 0. |
| Average or rate with no eligible values | N/A. |
| Percentages | One decimal place, rounding to the nearest value and upward at exact ties. |
| Positive duration below one minute | `< 1 min`. |
| Other durations | Complete days, hours, and minutes; discard remaining fractional minutes for presentation only. |

For example, a computed 12.25% displays as 12.3%; 90 seconds displays as 1 minute. Calculate averages and classifications from the complete values before formatting.

## Windows validation

| ID | Requirement | Acceptance scenario |
| --- | --- | --- |
| REQ-035 | Use Windows 11 version 25H2 as the reference test environment, a 1920 × 1080 display with 16:9 aspect ratio, and 100%, 125%, and 150% display scaling. Support resizing from a minimum of 960 × 540 logical units to maximized. Content and controls must remain accessible throughout that range, with no clipping or overlapping that prevents use. | Verify the minimum and maximized window states and resizing between them at each scale. At 150%, the minimum logical dimensions correspond to 1440 × 810 physical pixels. Task actions, deadline information, and dashboard controls remain usable. |

This is the MVP validation baseline. Broader desktop and responsiveness improvements belong to the [Backlog](backlog.md).

## Scope boundary

Only the requirements in this document define MVP behavior. [Scope](scope.md#mvp-boundaries) owns exclusions. The [Backlog](backlog.md) must not supply MVP requirements or acceptance criteria. Additional task organization features require an explicit scope decision.

## Open questions

No unresolved MVP product-behavior decisions remain. Future technical decisions are owned by [AGENTS.md](../../AGENTS.md#open-questions) and must be addressed in the relevant design after its behavioral specification is approved.

# Domain vocabulary

This document defines shared terms for the Task Analyzer MVP. [Requirements](requirements.md) defines behavior, calculations, and acceptance scenarios; [Scope](scope.md) defines product boundaries and component responsibilities. The vocabulary does not prescribe classes, database structures, or interfaces.

## Product and task lifecycle

| Term | Meaning | Behavioral reference |
| --- | --- | --- |
| Task Analyzer | The personal task-management and analysis product. | [Scope](scope.md#objective) |
| Desktop App | The Windows component used to interact with the product and view server results. | [Component responsibilities](scope.md#component-responsibilities) |
| Task Analyzer Server | The component responsible for business rules, persistent task state, and analysis. | [Component responsibilities](scope.md#component-responsibilities) |
| Task | A unit of personal work managed by the user. | [Tasks, REQ-007](requirements.md#tasks-and-server-persistence) |
| Title | The required text naming a task. A title is not the task's identity. | [REQ-007](requirements.md#tasks-and-server-persistence) and [REQ-029](requirements.md#task-uniqueness) |
| Description / observations | Optional explanatory text about a task; both names refer to the same concept. | [Tasks, REQ-007 and REQ-009](requirements.md#tasks-and-server-persistence) |
| Task status | Whether a task is pending or completed, separately from its deadline emphasis. | [Tasks, REQ-007](requirements.md#tasks-and-server-persistence) |
| Pending task | A task that has not been completed or has been successfully reopened. | [Task lifecycle, REQ-008](requirements.md#tasks-and-server-persistence) |
| Completed task | A task marked as finished. Its completion may be on time or late when it has a deadline. | [REQ-008](requirements.md#tasks-and-server-persistence) and [REQ-011](requirements.md#time-and-deadlines) |
| Reopening | Returning a completed task to pending status, subject to validation of the resulting state. | [REQ-008](requirements.md#tasks-and-server-persistence) and [REQ-029](requirements.md#task-uniqueness) |
| Deletion | Removing a task from managed work. It no longer contributes to metrics or uniqueness checks. This term does not prescribe a physical storage operation. | [REQ-025](requirements.md#productivity-metrics) and [REQ-029](requirements.md#task-uniqueness) |
| Equivalent titles | Titles considered equal by the server's comparison rule. | [REQ-029](requirements.md#task-uniqueness) |
| Duplicate task | A different task that conflicts under the combination of title equivalence, deadline, and participating status. | [REQ-029 and its eligibility table](requirements.md#task-uniqueness) |
| Server persistence | Retention of task data and lifecycle changes by the Task Analyzer Server. | [Persistence, REQ-010](requirements.md#tasks-and-server-persistence) |

## Operations and temporary input

| Term | Meaning | Behavioral reference |
| --- | --- | --- |
| Operation attempt | A submitted user action whose result can be consulted and whose repetition must not apply it again. | [Operation outcomes, REQ-031](requirements.md#commands-operation-outcomes-and-temporary-input) |
| Confirmed success | A server-confirmed result that establishes persistence of the requested change. | [REQ-031](requirements.md#commands-operation-outcomes-and-temporary-input) |
| Rejection | A server result that declines the requested change, such as a task-uniqueness conflict. | [REQ-029](requirements.md#task-uniqueness) and [REQ-031](requirements.md#commands-operation-outcomes-and-temporary-input) |
| Unconfirmed result | An operation outcome the desktop cannot yet establish. It does not mean the server cancelled or rejected the action. | [REQ-031](requirements.md#commands-operation-outcomes-and-temporary-input) |
| Temporary form input | Text and other form values held in desktop memory while the form remains open. | [REQ-032](requirements.md#commands-operation-outcomes-and-temporary-input) |
| Unsent changes | Form edits that have not been submitted to the server. | [REQ-030 and REQ-032](requirements.md#commands-operation-outcomes-and-temporary-input) |

## Time and deadlines

| Term | Meaning | Behavioral reference |
| --- | --- | --- |
| Original creation time | The server-recorded time of the task's first creation, retained as the starting point for completion measurements. | [REQ-028](requirements.md#time-and-deadlines) and [REQ-022/REQ-025](requirements.md#productivity-metrics) |
| Completion time | The server-recorded time when the task was completed. Measurements use the latest completion after a successful reopening and completion again. | [REQ-028](requirements.md#time-and-deadlines) and [REQ-025](requirements.md#productivity-metrics) |
| Product time zone | The fixed time-zone reference used by the server to interpret dates and deadline cutoffs. | [REQ-028](requirements.md#time-and-deadlines) |
| Product date | The calendar date obtained from server time in the product time zone. | [REQ-028](requirements.md#time-and-deadlines) |
| Deadline | An optional calendar date by which a task is intended to be completed. | [REQ-011](requirements.md#time-and-deadlines) |
| Deadline cutoff | The instant at which a calendar-date deadline expires. | [REQ-011](requirements.md#time-and-deadlines) |
| Deadline window | The interval between original creation and the deadline cutoff used in completion analysis. | [REQ-023](requirements.md#productivity-metrics) |
| Deadline emphasis | The server-derived indication of a pending task's relationship to its deadline. | [State definitions, REQ-026](requirements.md#visual-deadline-emphasis-and-refresh) |
| Currently overdue task | A pending task whose deadline cutoff has been reached. This is distinct from a late completion. | [REQ-011](requirements.md#time-and-deadlines) and [REQ-026](requirements.md#visual-deadline-emphasis-and-refresh) |
| Late completion | Completion at or after the deadline cutoff. | [REQ-011](requirements.md#time-and-deadlines) and [REQ-024](requirements.md#productivity-metrics) |
| On-time completion | Completion before the deadline cutoff for a task with a deadline. | [REQ-024](requirements.md#productivity-metrics) |

## Analysis and presentation

| Term | Meaning | Behavioral reference |
| --- | --- | --- |
| All-history analysis | Analysis covering task history without a reporting-period filter, subject to each metric's eligibility rules. | [REQ-021 through REQ-025](requirements.md#productivity-metrics) |
| Task counts | Totals for all, pending, and completed tasks. | [REQ-021](requirements.md#productivity-metrics) |
| Completion duration | Elapsed time from original creation to completion; it does not measure active work time. | [REQ-022](requirements.md#productivity-metrics) |
| Average completion duration | The average of eligible completed-task durations. | [REQ-022](requirements.md#productivity-metrics) |
| Deadline-window percentage | The share of the available deadline window consumed by completion. | [REQ-023 and its formula](requirements.md#productivity-metrics) |
| Average deadline-window percentage | The average of eligible completed-task deadline-window percentages. | [REQ-023](requirements.md#productivity-metrics) |
| Overdue rate | The share of completed tasks with deadlines that were completed late, excluding deleted tasks. | [REQ-024](requirements.md#productivity-metrics) |
| Eligible task or value | A task or calculated value included in a particular metric under that metric's rules. Eligibility differs between metrics. | [REQ-022 through REQ-025](requirements.md#productivity-metrics) |
| N/A | An unavailable metric value because its required inputs or eligible population are absent or invalid. | [REQ-023](requirements.md#productivity-metrics) and [REQ-033](requirements.md#metric-presentation) |
| Metrics dashboard | The dedicated desktop area containing the server-derived indicators and interactive charts. | [REQ-033](requirements.md#metric-presentation) |

## Open questions

No unresolved MVP domain definitions remain. Technical representation choices belong in the relevant designs and are tracked in [AGENTS.md](../../AGENTS.md#open-questions).

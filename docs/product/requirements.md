# MVP requirements

These requirements record the approved product scope. Each ID provides a reference for future specifications and tests. Acceptance scenarios below describe expected outcomes; they are not executed tests. Unresolved behavior is listed under Open questions and must be settled before implementing the affected behavior.

## Platform and account

| ID | Requirement | Acceptance scenario |
| --- | --- | --- |
| REQ-001 | Provide a Windows desktop application for individual users managing personal work. | A user manages personal tasks and views their metrics in the Windows application. |
| REQ-002 | Require an account for initial setup, then permit continued offline use on that installation. | After account setup, the user can work on tasks without connectivity. |
| REQ-003 | Run the backend on a dedicated, self-hosted server using Python 3.11 or later. | The deployment design supports the specified hosting arrangement and minimum Python version; other implementation technologies remain undecided. |
| REQ-004 | Maintain one authorized installation per account. A sign-in attempt on another PC must warn that an installation is already authorized and require explicit confirmation to replace it. | A second PC cannot replace the authorized installation without confirmation; confirmed replacement revokes the previous installation's cloud access. |
| REQ-005 | Allow recovery of tasks, metrics, and settings from the latest cloud backup on the replacement installation. | After confirmed replacement, the user can restore the most recently backed-up data. Edits never saved to the cloud are not recovered from it. |
| REQ-006 | Reject cloud writes from revoked installations. Rejected writes must not erase their local data. Reusing a revoked installation requires explicit replacement of the active installation and restoration from the cloud, with confirmation before discarding existing local edits. Do not merge installation histories in the MVP. | An old PC may continue working while offline, but its next cloud save is rejected. Its local edits remain until the user explicitly confirms their replacement during restoration. |

## Tasks and local persistence

| ID | Requirement | Acceptance scenario |
| --- | --- | --- |
| REQ-007 | A task has a required title, optional description/observations, optional deadline, pending/completed status, and an automatically determined priority state. | A task can be created with a title and no description or deadline; a task without a title cannot be created. |
| REQ-008 | Allow users to create, edit, complete, reopen, and delete tasks. | A pending task can be edited and completed, then reopened; a deleted task is excluded from metrics. |
| REQ-009 | Allow description/observation edits on completed tasks without reopening. Require reopening before changing the title, deadline, or reminder settings. Description edits preserve completion time and recorded priority. | Editing a completed task's observations leaves its completion measurements unchanged; editing its deadline requires reopening it. |
| REQ-010 | Persist offline and unsaved edits locally so they survive closing and reopening the application. | A user closes the app after making edits without a cloud save; reopening retains those edits, including while offline. |
| REQ-011 | Use a calendar date for the deadline. The cutoff is midnight immediately after that date in the account's time zone, initially taken from the setup machine. A pending task becomes overdue at the cutoff. | A task due on a given date remains within its deadline during that date and becomes overdue at the following midnight if incomplete. |

## Manual cloud backup

| ID | Requirement | Acceptance scenario |
| --- | --- | --- |
| REQ-012 | Save tasks, metrics, and settings to the cloud only when the user invokes a manual save action, such as "Save to cloud." Automatic background synchronization is outside the MVP. | Local task edits persist without a cloud save; invoking the action while authorized and connected updates the cloud backup. |
| REQ-013 | Visibly indicate local changes that have not been saved to the cloud. | A local change produces an unsaved-changes indication that remains while the change is absent from the cloud backup. |
| REQ-014 | Email scheduling uses the latest task data available to the server. Local changes that have not been saved to the cloud may leave server reminders outdated. | Completing a task locally without saving it may still result in an email based on the server's incomplete version. |

## Reminders and priority

| ID | Requirement | Acceptance scenario |
| --- | --- | --- |
| REQ-015 | For each task with a deadline, allow any combination of reminders 7, 3, and 1 calendar days before the deadline, or no reminders. Allow selection of the in-app channel, email, or both. | A user can select 7-day and 1-day reminders through both channels, or disable reminders for the task. |
| REQ-016 | Schedule reminders at 09:00 in the account's time zone on each selected reminder date. | A 3-day reminder for a September 14 deadline becomes due at 09:00 on September 11 in the account's time zone. |
| REQ-017 | Present in-app notifications in a notifications tab. Email reminders go to the account's registered email address and can be sent while the desktop application is closed. Previously generated in-app notifications remain available when it is reopened. | With the app closed, the server can send a scheduled email; reopening the app preserves previously generated in-app notifications. |
| REQ-018 | Use exactly two priority states: non-priority by default, and priority when the first selected reminder becomes due. Promotion is automatic and independent of app availability or email delivery success. Do not allow manual priority changes. Tasks without reminders remain non-priority. | A task with 7-day and 1-day reminders becomes priority at the 7-day trigger even if email delivery fails; a task with no reminders stays non-priority. |
| REQ-019 | Recalculate priority for pending tasks from their current deadline and selected reminders after relevant edits. Preserve priority at completion for metrics; recalculate it when reopened. | Moving a pending task's first reminder into the future returns it to non-priority. Completing it preserves its then-current priority for reporting. |
| REQ-020 | When creation or rescheduling places selected reminder times in the past, immediately recalculate priority without sending retroactive email reminders. Future selected reminders still occur normally. | A task created after its selected 7-day trigger is immediately priority, receives no catch-up 7-day email, and remains eligible for its future selected 1-day reminder. |

## Productivity metrics

| ID | Requirement | Acceptance scenario |
| --- | --- | --- |
| REQ-021 | Show task counts, average completion duration, average deadline-window percentage, and overdue rate, overall and grouped by non-priority/priority. Cover all task history in the MVP. | The user can inspect overall measurements and the corresponding measurements for each priority state. |
| REQ-022 | Measure completion duration as completion time minus original creation time; average durations across completed, non-deleted tasks. | Tasks completed after 2 and 4 hours produce an average completion duration of 3 hours. Pending tasks do not enter this average. |
| REQ-023 | Calculate each completed task's deadline-window percentage using the formula below. Show N/A without a deadline or if its cutoff is at or before creation. Average valid percentages of completed, non-deleted tasks for the aggregate indicator. | Completion halfway through a valid deadline window yields 50%; completion after 1.5 times that window yields 150%. An invalid or absent window is excluded from the average. |
| REQ-024 | Measure overdue rate as the percentage of eligible tasks with deadlines that missed them: completed late or still incomplete after the deadline. Exclude tasks without deadlines and deleted tasks. Eligibility of future-deadline tasks in the denominator remains open. | A completed-late task and a pending task past its cutoff count as missed deadlines; a task without a deadline does not enter the calculation. Final denominator tests await the open decision. |
| REQ-025 | Exclude deleted tasks from all metrics. Reopening removes a task from completed-task calculations until it is completed again, using its original creation time and latest completion time. Use current priority for pending tasks and preserved completion priority for completed tasks. | Reopening a task removes its prior completion duration and percentage from averages. Completing it again measures from its original creation time to the new completion time. |

The deadline-window percentage is:

```text
[(completion time - creation time) / (deadline cutoff - creation time)] * 100
```

The deadline cutoff is defined in REQ-011. The percentage expresses how much of the available deadline window was consumed; it is not a task-progress percentage. Values above 100% indicate completion after the deadline. No cap at 100% is applied.

## Scope exclusions

All items in [Backlog](backlog.md) are future possibilities, not MVP requirements. Additional task organization features also require an explicit scope decision. Python 3.11+ is selected for the server. Client languages, frameworks, databases, authentication technology, and deployment tooling remain undecided.

## Open questions

- **OQ-001 — Authentication and recovery:** How do registration, sign-in, email verification, password/account recovery, and sign-out work? What local access remains after explicit sign-out?
- **OQ-002 — Installation replacement:** What information identifies the already authorized machine in the warning? What happens if replacement or restoration fails, or no cloud backup exists yet?
- **OQ-003 — Notification lifecycle:** What are the retention and read/unread rules? How are in-app reminders generated or caught up while the app is closed/offline? Are catch-up in-app reminders created when selected reminder times already passed before task creation or rescheduling?
- **OQ-004 — Reminder changes:** How should completion, reopening, deletion, channel changes, and repeated rescheduling affect existing notifications and future delivery? How are duplicate delivery and delivery failures handled?
- **OQ-005 — Time-zone changes:** Can users change the account time zone after setup? How would changes affect existing deadlines, reminder schedules, and historical metrics?
- **OQ-006 — Empty metrics:** What is displayed when there are no eligible values for a count, average, or rate? What duration units and percentage precision should be displayed?
- **OQ-007 — Overdue denominator:** Do tasks with future deadlines enter the overdue-rate denominator immediately, or only after completion or reaching their cutoff? How is completion exactly at the cutoff classified?
- **OQ-008 — Cloud-save lifecycle:** What feedback and retry behavior apply to failed saves? How are edits made during a save represented? How does the client receive server-generated notification information while task backup remains manual?
- **OQ-009 — Detailed task interaction:** What validation limits apply to text and dates? Are deletion confirmation and recovery needed? What default reminder/channel selections apply to a new task?
- **OQ-010 — Technical options:** With Python 3.11+ selected for the server, which Windows UI framework, local persistence mechanism, Python backend framework, database, authentication mechanism, and email delivery approach should be evaluated? These remaining options need a later comparison against the approved product behavior; none is selected.

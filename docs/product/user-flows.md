# User flows

These flows describe approved MVP interactions and refer to [Requirements](requirements.md). Unresolved steps remain explicit questions rather than assumed behavior.

## 1. Set up the first installation

1. The user creates or accesses an account during initial setup.
2. The application initially takes the account time zone from the setup machine.
3. The user manages personal tasks on the authorized installation and can continue working offline afterward.

Requirements: REQ-001, REQ-002, REQ-004, REQ-011. Authentication details remain open.

## 2. Create and edit a task

1. The user supplies a required title and optionally adds a description/observations and a calendar-date deadline.
2. For a task with a deadline, the user can select reminders 7, 3, and/or 1 days before the deadline, or none, and choose in-app notifications, email, or both.
3. The task is pending. Its priority is determined automatically from the deadline and selected reminders.
4. Edits persist locally, including offline or unsaved edits, and survive closing the app.
5. The application indicates changes that have not been saved to the cloud.

Requirements: REQ-007, REQ-008, REQ-010, REQ-011, REQ-013, REQ-015, REQ-018 through REQ-020.

## 3. Save work to the cloud

1. The user invokes the manual cloud-save action from the authorized installation.
2. A successful save updates the cloud backup of tasks, metrics, and settings.
3. Local changes not included in the cloud backup remain visibly identified as unsaved.
4. The server uses its latest task data for email reminders. Until a local edit reaches the cloud, emails may reflect older deadlines or task status.

Requirements: REQ-012 through REQ-014. Save failure and concurrent-edit handling remain open; automatic background backup is outside the MVP.

## 4. Receive reminders and become priority

1. A selected reminder becomes due at 09:00 on its reminder date in the account's time zone.
2. When the first selected reminder becomes due, the task becomes priority regardless of whether the app is open or email delivery succeeds.
3. Notifications use the selected channels. Email can arrive while the app is closed, using server-known task data.
4. The user can return to previously generated notifications in the in-app notifications tab after reopening the app.
5. If the user creates or reschedules a task after a selected reminder time, priority is recalculated immediately. No retroactive email is sent; future selected reminders still occur.

Requirements: REQ-014 through REQ-020. Generation and catch-up of in-app reminders while offline or closed remain open.

## 5. Complete, annotate, reopen, or delete a task

1. The user completes a pending task. Its completion time and priority at completion support the metrics.
2. The user may edit its description/observations while it remains completed, preserving completion time and recorded priority.
3. To change its title, deadline, or reminder settings, the user first reopens it.
4. Reopening recalculates priority and removes the task from completed-task metric calculations.
5. Completing it again uses its original creation time and latest completion time.
6. Deleting the task excludes it from all metrics.

Requirements: REQ-008, REQ-009, REQ-019, REQ-022 through REQ-025.

## 6. Replace the authorized machine

1. The user attempts to sign in on another PC.
2. The application warns that the account already has an authorized installation and requires explicit confirmation to replace it.
3. After confirmation, the new installation is authorized and the previous installation loses cloud access.
4. The user restores tasks, metrics, and settings from the latest cloud backup. Unsaved data on the previous machine is not part of that backup.
5. If the old installation continues offline, it may retain local work, but its next cloud write is rejected without erasing that work.
6. To use that old installation with cloud access again, the user must explicitly replace the currently authorized installation and restore the cloud version. Discarding existing local edits requires confirmation.

Requirements: REQ-004 through REQ-006. The MVP provides no merge flow.

## 7. Review productivity

1. The user views all-history task counts, average completion duration, average deadline-window percentage, and overdue rate.
2. The user inspects the overall values and values grouped by non-priority/priority.
3. Completed-task averages exclude pending and deleted tasks. Deadline-window percentages additionally exclude absent or invalid deadline windows.
4. The overdue rate excludes tasks without deadlines and deleted tasks; its remaining denominator eligibility rule is awaiting definition.

Requirements: REQ-021 through REQ-025. Additional metrics are future work.

## Open questions

- What are the detailed registration, recovery, sign-out, and installation-restoration flows, including failure cases? See OQ-001 and OQ-002 in [Requirements](requirements.md#open-questions).
- How do notification read status, retention, catch-up, and changes to task state affect the notification experience? See OQ-003 and OQ-004.
- How are time-zone changes, empty metrics, and overdue-denominator eligibility presented? See OQ-005 through OQ-007.
- What feedback accompanies cloud-save failures, edits during saving, task validation, and deletion? See OQ-008 and OQ-009.

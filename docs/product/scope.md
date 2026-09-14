# MVP scope

## Objective

Task Analyzer is a personal task-management and analysis product composed of the **Desktop App** and the **Task Analyzer Server**. The MVP prioritizes the server's business rules, persistence, and analysis. The Windows desktop provides the interaction and presentation needed to use those capabilities.

This document defines the intended outcomes, MVP boundary, component responsibilities, and completion criterion. [Requirements](requirements.md) defines detailed behavior and acceptance scenarios.

## MVP boundaries

- Manage personal tasks through creation, editing, completion, reopening, and deletion, with optional observations and calendar-date deadlines.
- Validate task data and uniqueness in the server, and retain task state there.
- Derive deadline emphasis and all-history productivity metrics in the server.
- Present tasks and a dedicated metrics dashboard with the charts and hover interactions defined in [Requirements](requirements.md#metric-presentation).
- Provide private personal access without product accounts, using the access arrangement in [Requirements](requirements.md#platform-and-access).
- Keep form input in memory during failures and distinguish confirmed, rejected, and unknown operation outcomes.
- Meet the [Windows validation baseline](requirements.md#windows-validation). The server is the MVP's main focus; broader desktop and responsiveness improvements are future work.

The MVP depends on server access. Product accounts/authentication, installation management, recovery, cloud backup, synchronization, offline operation, multiple-machine use, persistent local drafts, reminders/notifications, automatic priority, and priority-grouped metrics are outside its boundary. These and other future capabilities are owned by the [Backlog](backlog.md). Server persistence does not imply a separate backup or synchronization feature.

## Component responsibilities

| Component | Responsibility |
| --- | --- |
| Task Analyzer Server | Validate task data and uniqueness; apply lifecycle and time rules; persist task state; recognize operation attempts and expose their results; derive deadline emphasis and calculate metrics. |
| Desktop App | Collect input; submit user actions; present server results and operation outcomes; preserve temporary form input while its window is open; provide task and dashboard interaction within the Windows baseline. |

The product's access relationship is:

```mermaid
flowchart LR
    person["Individual user"] --> desktop["Desktop App"]
    desktop <-->|Private access through Tailscale| server["Task Analyzer Server"]
```

The [platform and access requirements](requirements.md#platform-and-access) define hosting and access constraints. Detailed deployment topology, connection setup, and the communication contract belong in the relevant design.

## Completion criterion

The MVP is complete when its [requirements and acceptance scenarios](requirements.md) are covered by approved feature specifications and verified through the Desktop App and Task Analyzer Server. Users must be able to manage persistent tasks, receive correct operation outcomes, see deadline emphasis, and review the defined metrics. The applicable requirement, regression, quality, and Windows UI checks must pass under [AGENTS.md](../../AGENTS.md#code-and-tests).

Backlog capabilities are not release prerequisites. The current state of development is recorded in the [README](../../README.md#current-project-status).

## Learning goals and vocabulary

This is a personal learning and portfolio project. Favor a development workflow and implementation that one person can understand and run.

- Description and observations name the same optional task text.
- A title is not task identity; title equivalence is only a uniqueness rule.
- Task status (pending/completed) is separate from deadline emphasis.
- Completion duration measures elapsed time since original creation, not active work time. Recompletion uses the latest completion timestamp.
- An unknown operation result does not mean cancellation, rejection or rollback. Temporary form input is memory-only.
- Deletion excludes a task from managed work, metrics and uniqueness; this does not prescribe physical storage deletion.

## Delivery order

| Capability | Dependencies |
| --- | --- |
| 1A: creation and pending edits | Validation, persistence, task identity, time and operation outcomes; implemented locally. |
| 1B: lifecycle and deletion | 1A contracts; adds completion, completed-observation editing, reopening and deletion. |
| Deadline emphasis / productivity analysis | Stable lifecycle, time and eligibility contracts; these two areas may be designed independently. |
| Windows task interaction / dashboard | Corresponding server contracts plus client setup, refresh and feedback decisions. |

Contract dependencies do not require finishing implementation before specifying dependent behavior. New features are currently paused. Detailed interactions, formulas, refresh timing and Windows acceptance scenarios remain in Requirements.

## Open questions

No unresolved MVP scope or component-responsibility decisions remain. Future technical decisions are maintained in [AGENTS.md](../../AGENTS.md#open-questions).

- Which measurable personal-use outcomes should evaluate product value after use begins? This does not block MVP acceptance.

# MVP scope

## Objective

Task Analyzer is a personal task-management and analysis product composed of the **Desktop App** and the **Task Analyzer Server**. The MVP prioritizes the server's business rules, persistence, and analysis. The Windows desktop provides the interaction and presentation needed to use those capabilities.

This document defines the MVP boundary, component responsibilities, and completion criterion. [Vision](vision.md) describes the intended outcomes; [Requirements](requirements.md) defines detailed behavior and acceptance scenarios.

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

The MVP is complete when its [requirements and acceptance scenarios](requirements.md) are covered by approved feature specifications and verified through the Desktop App and Task Analyzer Server. Users must be able to manage persistent tasks, receive correct operation outcomes, see deadline emphasis, and review the defined metrics. The applicable requirement, regression, quality, and Windows UI checks must pass under [AGENTS.md](../../AGENTS.md#tests-and-verification).

Backlog capabilities are not release prerequisites. The current state of development is recorded in the [README](../../README.md#current-project-status).

## Open questions

No unresolved MVP scope or component-responsibility decisions remain. Future technical decisions are maintained in [AGENTS.md](../../AGENTS.md#open-questions).

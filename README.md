# Task Analyzer

## Product description

Task Analyzer is a Windows desktop TODO application for individual users managing personal work. It turns task history into productivity metrics that help users understand completion patterns and missed deadlines.

See the [product vision](docs/product/vision.md), [requirements](docs/product/requirements.md), and [user flows](docs/product/user-flows.md) for the agreed product definition. The scope below describes planned behavior, not currently available functionality.

## MVP scope

- **Task management:** create, edit, complete, reopen, and delete tasks with a required title, optional description/observations, and optional calendar-date deadline. Completed tasks allow observation edits; other edits require reopening.
- **Automatic priority:** tasks start as non-priority and become priority when their first selected deadline reminder becomes due, independent of notification delivery. Tasks without reminders remain non-priority. Pending-task priority is recalculated after relevant changes; completed tasks preserve their priority for metrics.
- **Productivity metrics:** all-history task counts, average completion duration, average deadline-window percentage, and overdue rate, overall and by priority. Completion duration runs from creation to completion. The percentage measures elapsed completion time relative to the available time before the deadline cutoff, and can exceed 100%.
- **Local persistence:** offline and unsaved edits survive closing and reopening the application.
- **Accounts and manual cloud backup:** an account is required for initial setup, followed by offline use. A manual save action backs up tasks, metrics, and settings to a dedicated, self-hosted server.
- **Machine replacement and recovery:** one authorized installation per account. Signing in on another PC warns about the existing installation and requires explicit replacement confirmation. The new installation can restore the latest cloud backup; the old installation cannot write to the cloud. Unsaved local edits are not included in recovery, and replacing them during restoration requires confirmation.
- **Deadline reminders:** select any combination of 7-, 3-, and 1-day reminders, or none, per task. Channels are the in-app notifications tab, email to the registered account address, or both. Reminders become due at 09:00 in the account's time zone; a deadline expires at midnight after its calendar date. Email can arrive while the app is closed, using the latest server-known task data, which may lag behind unsaved local changes.

Detailed calculation rules and unresolved cases are recorded in the [requirements](docs/product/requirements.md), including the overdue-rate denominator.

## Outside the MVP

- WhatsApp bot with task commands and deadline reminders.
- Full browser-based web version.
- Mobile application.
- Gamification.
- Integration with a separate financial system that has not yet been built.
- Automatic background cloud synchronization.
- Additional productivity metrics beyond the approved initial set.

These are future possibilities in the [backlog](docs/product/backlog.md), not MVP requirements or release commitments. Concurrent authorized installations and merging changes between machines are also outside the MVP. Additional task organization features require an explicit scope decision.

## Current project status

The project is in product definition. Product documentation and working guidelines are written; application code, executable tests, and build/deployment configuration have not been implemented. Existing feature-specification files are empty scaffolding, not implementation-ready specifications.

Python 3.11+ is the only selected implementation technology and applies to the server. The Windows client technology, backend framework, databases, authentication technology, and other tooling remain undecided. There is no runnable application or setup procedure yet.

Development follows Spec-Driven Development: specification, design, plan, tasks, implementation, tests, and verification. Specifications under `specs/` are the source of truth for application behavior. Every requirement and acceptance criterion must have corresponding tests before implementation is considered complete. Read [AGENTS.md](AGENTS.md) for working rules and approval requirements.

## Folder structure

The current workspace contains the following structure. Empty scaffold directories may not appear in a Git checkout until files are added.

```text
task-analyzer/
|-- .ai/skills/             # Local interview skills
|-- .vscode/               # Local editor settings; ignored by Git
|-- docker/                # Empty scaffold; no tooling decision implied
|-- docs/
|   |-- architecture/      # Empty architecture documentation scaffold
|   `-- product/
|       |-- vision.md
|       |-- requirements.md
|       |-- user-flows.md
|       `-- backlog.md
|-- specs/
|   |-- 01-[SpecName]/      # Empty feature-specification scaffold
|   |   |-- spec.md
|   |   |-- design.md
|   |   |-- plan.md
|   |   `-- tasks.md
|   `-- 02-[SpecName]/      # Same four empty specification files
|-- src/
|   |-- app/               # Empty client source scaffold
|   `-- server/            # Empty server source scaffold
|-- tests/                 # Empty test scaffold
|-- .gitignore
|-- AGENTS.md              # Development and collaboration rules
|-- CLAUDE.md              # Local reference to AGENTS.md; ignored by Git
`-- README.md
```

## Open questions

- Which Windows versions, window sizes, and display-scaling settings will be supported?
- How should authentication, account recovery, and installation-restoration failure cases work?
- What are the notification retention, read-status, catch-up, and time-zone-change rules?
- Should future-deadline tasks enter the overdue-rate denominator, and how should empty metrics and numerical precision be displayed?
- What feedback and retry behavior should apply to failed cloud saves and edits made during saving?
- Which client, backend, storage, email, testing, and deployment options should be evaluated alongside server-side Python 3.11+?

See the full unresolved decisions in [product requirements](docs/product/requirements.md#open-questions), [product vision](docs/product/vision.md#open-questions), [user flows](docs/product/user-flows.md#open-questions), [backlog](docs/product/backlog.md#open-questions), and [working guidelines](AGENTS.md#open-questions).

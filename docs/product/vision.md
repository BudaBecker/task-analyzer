# Product vision

Task Analyzer is a Windows desktop TODO application that derives productivity metrics from tasks. It helps individual users managing personal work understand completion patterns and missed deadlines.

## Problem and intended outcomes

Users need to manage their work and understand how quickly tasks are completed, how often deadlines are missed, and how results differ by priority. Task Analyzer brings task management and those measurements into one product.

The intended outcomes are to help users recognize those patterns, keep their work available while offline, and recover their latest cloud-backed-up data when moving to another machine. Numerical product success targets have not been defined.

## MVP product boundaries

- A desktop application for Windows, with an account required during initial setup and continued offline use on that installation.
- Personal tasks with a title, optional description/observations, optional calendar-date deadline, pending/completed status, and automatic non-priority/priority classification.
- Task counts, average completion duration, average deadline-window percentage, and overdue rate, overall and by priority, across all task history.
- Locally persistent work, including offline and unsaved edits that survive closing the application.
- Manual cloud backup of tasks, metrics, and settings through a dedicated action. The backend runs on a dedicated, self-hosted server.
- One authorized installation per account, with explicit replacement and recovery from the latest cloud backup on another machine.
- Configurable deadline reminders through an in-app notifications tab and email to the account's registered address.

The MVP does not merge changes from multiple machines. A revoked installation cannot write to the cloud. Manual backup means the server can have older task information and send reminders based on that older information.

## Documentation and development status

The project is in product definition; application implementation has not started. Python 3.11+ is selected for the server; all other stack choices remain open. These documents record approved product decisions for subsequent specification work. Specifications under `/specs` remain the source of truth for application behavior before implementation.

- [Requirements](requirements.md) records numbered MVP requirements and acceptance scenarios.
- [User flows](user-flows.md) describes the agreed interactions and their requirement references.
- [Backlog](backlog.md) records future work outside the MVP.

## Open questions

- What measurable adoption or user-outcome targets will define product success?
- Which Windows versions will the MVP support?
- What authentication and account-recovery experience should the product provide?
- Detailed unresolved behavior is listed in [Requirements](requirements.md#open-questions). Which technologies should complement the approved server-side Python 3.11+ decision?

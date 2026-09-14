# Product backlog

Every item in this document is outside the MVP. Do not use this backlog as input for MVP requirements, acceptance criteria, specifications, designs, plans, or implementation tasks. Backlog questions do not block MVP specification work. Moving any capability into scope requires explicit user approval and a new product definition.

The current product boundary belongs to [Scope](scope.md); product behavior and acceptance scenarios belong to [MVP requirements](requirements.md).

## Future possibilities

| ID | Item | Future possibility |
| --- | --- | --- |
| FUT-001 | WhatsApp bot | Task commands `!tarefas`, `!deadline`, and `!todo`, plus deadline reminders. These are proposed command names; detailed behavior remains undefined. |
| FUT-002 | Full web version | Access the product through a browser. |
| FUT-003 | Mobile application | Provide a mobile version of the product. |
| FUT-004 | Gamification | Explore mechanics that support the intended user outcomes. |
| FUT-005 | Financial-system integration | Integrate with a separate financial system that has not yet been built. |
| FUT-006 | Synchronization | Explore synchronization and define its relationship with server persistence, backup, offline work, and multiple-machine use. |
| FUT-007 | Additional productivity metrics | Explore measurements beyond the MVP metric set. |
| FUT-008 | Accounts and authentication | Define user identity, account setup, sign-in, and sign-out. |
| FUT-009 | Installation management | Define registration, authorization, replacement, and revocation of installations if needed. |
| FUT-010 | Recovery | Explore account recovery, data restoration, and recovery of deleted tasks. |
| FUT-011 | Cloud backup | Explore backup of product data, including whether a manual save action is useful. Server persistence is already part of the MVP and does not imply backup. |
| FUT-012 | Offline operation and persistent local drafts | Explore use without server access and preservation of unsaved input after closing the desktop. |
| FUT-013 | Multiple-machine use | Explore using personal task data from more than one desktop installation. |
| FUT-014 | Reminders and notifications | Explore deadline reminders and notification channels, including in-app and email delivery. |
| FUT-015 | Automatic priority and priority-grouped metrics | Explore task priority and analysis grouped by priority. |
| FUT-016 | Desktop experience and broader responsiveness | Improve the desktop experience beyond the [MVP Windows validation baseline](requirements.md#windows-validation), with greater focus on interface and responsiveness after the MVP. |

These descriptions establish no detailed behavior, delivery order, or release commitment. Each capability needs its own decisions if explicitly brought into scope.

## Open questions

All questions below concern future work outside the MVP.

### Deferred product behavior

- **Backlog planning:** What priority, release order, and success criteria should apply to future capabilities?
- **FUT-001:** What would each WhatsApp command return or change, and how would it identify the user?
- **FUT-002/FUT-003:** What behavior and platform coverage would web and mobile versions require?
- **FUT-004:** Which gamification mechanics would support the intended user outcomes?
- **FUT-005:** What data and responsibilities would the financial-system integration share?
- **FUT-006/FUT-011:** What would synchronization and backup each cover? When would they run, how would unsaved or failed operations be presented, and what consistency and conflict rules would apply?
- **FUT-007:** Which additional metrics would provide useful information?
- **FUT-008:** How would registration, sign-in, verification, sign-out, and access to existing data work?
- **FUT-009/FUT-013:** Which installation and concurrent-use policies would be appropriate? How would replacement, revocation, and failures affect access and existing work?
- **FUT-010:** What account or data recovery would be supported, including deleted tasks? What would be restored when backups are missing or incomplete?
- **FUT-012/FUT-013:** How would local edits and changes from different machines relate to the server's task data? What protection would existing local work need?
- **FUT-014:** Which reminder schedules, channels, and defaults would be useful? How would time zones, task changes, notification retention/read status, catch-up, duplicate delivery, and failures be handled?
- **FUT-015:** How would priority be determined, how would it relate to deadline emphasis, and how would lifecycle changes affect priority-grouped metrics?
- **FUT-016:** Which usability improvements, window sizes, display resolutions, and scaling settings should extend the MVP desktop baseline?

### Future technical decisions

- Which authentication, local persistence, backup, synchronization, and notification-delivery options should be evaluated if their associated product capabilities are approved?
- Technical decisions for the MVP are maintained separately in [AGENTS.md](../../AGENTS.md#open-questions). No technical choice for a deferred capability is an MVP prerequisite.

- A possible PostgreSQL migration is a future learning idea, not an MVP requirement. Evaluate it only in a separately approved scope; do not build a second persistence implementation in anticipation.

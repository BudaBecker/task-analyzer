# Product backlog

Every item in this document is outside the MVP. These are future possibilities, not requirements, commitments, or an implementation sequence. Moving any item into scope requires an explicit product decision and corresponding specification work.

## Future possibilities

| ID | Item | Recorded intent |
| --- | --- | --- |
| FUT-001 | WhatsApp bot | Task commands `!tarefas`, `!deadline`, and `!todo`, plus deadline reminders. The command tokens retain the exact proposed interface names; their detailed behavior is undefined. |
| FUT-002 | Full web version | Access the complete product through a browser. |
| FUT-003 | Mobile application | Provide a mobile version of the product. |
| FUT-004 | Gamification | Explore gamification; mechanics and intended outcomes are undefined. |
| FUT-005 | Financial-system integration | Integrate with a separate financial system that has not yet been built. |
| FUT-006 | Automatic cloud synchronization | Consider replacing manual-only cloud saving with background synchronization after manual saving works reliably. Reliability criteria and synchronization rules are undefined. |
| FUT-007 | Additional productivity metrics | Extend the approved initial metric set through future product decisions. No additional metric is currently specified. |

## MVP boundary

The MVP is a Windows desktop product with manual cloud backup and one authorized installation per account. It includes only the metric set and reminder channels defined in [Requirements](requirements.md). The existence of a backlog item does not authorize application code, stack selection, or additional MVP behavior.

## Open questions

- What priority, release order, and success criteria should apply to these future possibilities?
- What does each WhatsApp command return or change, and how would it authenticate the user?
- What product behavior and platform coverage would web and mobile versions require?
- Which gamification mechanics would support the intended user outcomes?
- What data and responsibilities would the future financial-system integration share?
- What evidence makes manual cloud saving reliable enough to consider automatic synchronization, and what conflict rules would then apply?
- Which additional metrics would provide useful information beyond the initial set?

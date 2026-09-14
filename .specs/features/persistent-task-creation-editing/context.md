# Persistent Task Creation and Editing Context

**Gathered:** 2026-09-13.
**Spec:** [spec.md](spec.md).
**Status:** Audit-time behavioral clarifications approved by the user.

## Feature Boundary

Delivery 1A retains creation, pending-task editing, persistence, uniqueness, product time, and recoverable operation outcomes. No lifecycle, desktop, or backlog capability is added.

## Implementation Decisions

### TIME-02: An entirely skipped following date

Use the first existing instant at or after the nominal next-day calendar boundary. For a `2011-12-29` deadline in `Pacific/Apia`, the cutoff is `2011-12-31T00:00:00+14:00`, or `2011-12-30T10:00:00Z`. The user explicitly approved this choice in the audit-correction round. PCE-50 and REQ-011 retain the ordinary September 14/15 scenario and repeated-midnight behavior.

### TIME-03: Representable deadline range

Accept calendar deadlines from `0001-01-01` through `9999-12-30`, inclusive. The user explicitly approved rejecting `9999-12-31`, rather than extending the chosen timestamp representation to year 10000. The technical field code is `INVALID_DEADLINE`; the rejection remains a durable task-validation result and preserves task state. PCE-51/52 supplement REQ-007/008; PCE-08/09 now refer to the supported range.

### Agent's Discretion

The user authorized correction and local versioning of the audited documentation. This does not approve application implementation, deployment, database changes, push, or merge.

### Declined or Undiscussed Gray Areas

None. Both behavioral questions received explicit answers; silence was not used as approval.

## Specific References

[IANA Australasia data](https://data.iana.org/time-zones/tzdb/australasia) records the skipped Samoa date. [Python datetime boundaries](https://docs.python.org/3.13/library/datetime.html#date.max) constrain the chosen cutoff representation.

## Deferred Ideas

None; the discussion stayed within delivery 1A.

## Open questions

No unresolved behavioral question from this audit remains. Technical corrections are tracked in [design.md](design.md); implementation tasks remain pending approval in [tasks.md](tasks.md).

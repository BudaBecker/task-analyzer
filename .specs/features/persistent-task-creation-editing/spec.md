# Persistent task creation and editing

Delivery 1A. Behavior and its temporal clarifications were approved on 2026-09-13. Implementation exists; maintenance and local verification are tracked in [maintenance](../../../docs/maintenance.md). Target-host and private-access evidence remain pending.

## Scope

Create and edit pending tasks, retain their state and original creation time, enforce uniqueness, keep a fixed product zone, and recover original operation outcomes. Product inputs: [requirements](../../../docs/product/requirements.md) and [scope](../../../docs/product/scope.md). Technical contracts live in [design](design.md).

Completion, reopening, completed-task observation edits and deletion belong to 1B. Metrics, deadline-emphasis presentation and the Windows client are separate features. No backlog capability is introduced. The desktop owns progress, its 15-second unconfirmed-result timer, Retry sequencing and unsent form input.

## Acceptance criteria

PCE identifiers supplement the original REQ identifiers; they do not replace them. Approved criteria are retained verbatim below.

### Create a valid pending task

1. WHEN a valid title-only creation is applied THEN the server SHALL create a pending task without requiring observations or a deadline. **PCE-01; REQ-007, REQ-008.**
2. IF a title is empty or whitespace-only THEN the server SHALL reject the operation. **PCE-02; REQ-007.**
3. WHEN a title has exactly 200 characters after trimming leading and trailing spaces THEN the server SHALL accept that title. **PCE-03; REQ-007.**
4. IF a title exceeds 200 characters after trimming leading and trailing spaces THEN the server SHALL reject the operation. **PCE-04; REQ-007.**
5. WHEN observations have exactly 5,000 characters THEN the server SHALL accept those observations. **PCE-05; REQ-007.**
6. IF observations exceed 5,000 characters THEN the server SHALL reject the operation. **PCE-06; REQ-007.**
7. WHEN accepted observations contain line breaks THEN the server SHALL retain those line breaks in the task's observations. **PCE-07; REQ-007, REQ-010.**
8. WHEN a valid calendar-date deadline within the supported range is supplied THEN the server SHALL retain that calendar date as the task's deadline. **PCE-08; REQ-007, REQ-011.**
9. WHEN a valid deadline within the supported range precedes the current product date THEN the server SHALL accept the past deadline. **PCE-09; REQ-007.**
10. IF a supplied deadline is not a valid calendar date THEN the server SHALL reject the operation. **PCE-10; REQ-007.**
11. The server SHALL count user-perceived characters when enforcing title and observation length limits. **PCE-48; REQ-007.**
12. WHEN a valid deadline is either `0001-01-01` or `9999-12-30` THEN the server SHALL accept that deadline subject to the other applicable task rules. **PCE-51; REQ-007.**
13. IF a deadline is outside the inclusive `0001-01-01` through `9999-12-30` range THEN the server SHALL reject the operation without changing task state. **PCE-52; REQ-007, REQ-008.**

### Edit a pending task without losing its identity or valid state

1. WHEN a valid edit to a pending task is applied THEN the server SHALL persist the requested title, observations, and deadline values. **PCE-11; REQ-007, REQ-008, REQ-010.**
2. WHEN a pending task is edited THEN the server SHALL preserve its task identity. **PCE-12; REQ-008, REQ-029.**
3. WHEN a pending task is edited THEN the server SHALL preserve its original creation time. **PCE-13; REQ-028.**
4. WHEN a content edit to a pending task is applied THEN the server SHALL retain pending status. **PCE-14; REQ-007, REQ-008.**
5. IF an edit violates task validation THEN the server SHALL reject it without changing the task's persisted state. **PCE-15; REQ-007, REQ-008.**
6. WHEN a valid edit removes optional observations or the optional deadline THEN the server SHALL persist the absence of the removed value. **PCE-16; REQ-007, REQ-008, REQ-010.**

### Enforce task uniqueness on creation and pending-task editing

1. The server SHALL compare titles without case differences, after trimming leading/trailing spaces and treating runs of internal spaces as one space. **PCE-17; REQ-029.**
2. The server SHALL preserve accent differences when comparing titles for uniqueness. **PCE-18; REQ-029.**
3. IF a creation or pending-task edit would produce a dated task conflicting with another pending or completed task with an equivalent title and the same deadline date THEN the server SHALL reject the operation. **PCE-19; REQ-029.**
4. IF a creation or pending-task edit would produce an undated pending task conflicting with another undated pending task with an equivalent title THEN the server SHALL reject the operation. **PCE-20; REQ-029.**
5. WHEN different tasks have equivalent titles and different deadline dates THEN the server SHALL permit their coexistence. **PCE-21; REQ-029.**
6. WHEN an undated task and a dated task have equivalent titles THEN the server SHALL permit their coexistence. **PCE-22; REQ-029.**
7. WHEN an existing task is edited without changing its uniqueness combination THEN the server SHALL exclude that task itself from conflict comparisons. **PCE-23; REQ-029.**
8. The server SHALL exclude deleted tasks from uniqueness comparisons. **PCE-24; REQ-029.**
9. WHEN creating or editing an undated pending task THEN the server SHALL exclude completed undated tasks from conflict comparisons. **PCE-25; REQ-029.**
10. IF an operation conflicts under the uniqueness rules THEN the server SHALL identify the uniqueness conflict in its rejection result. **PCE-26; REQ-029, REQ-031.**
11. IF an operation is rejected for a uniqueness conflict THEN the server SHALL leave both the target task, if any, and the conflicting task unchanged. **PCE-27; REQ-008, REQ-029.**

### Retain authoritative task state and product time

1. WHEN a task creation is applied THEN the server SHALL record its original creation time from the server's clock at application of that operation. **PCE-28; REQ-028.**
2. WHEN the product time zone is supplied by the desktop during initial configuration THEN the server SHALL retain that zone as the fixed product time zone for the MVP. **PCE-29; REQ-028.**
3. The server SHALL determine the current product date from server time in the retained product time zone. **PCE-30; REQ-028.**
4. WHEN the desktop's clock or time zone changes after initial configuration THEN the server SHALL preserve the server-based timestamp and deadline interpretation rules. **PCE-31; REQ-028.**
5. The server SHALL interpret a deadline's cutoff as midnight immediately after its calendar date in the product time zone. **PCE-32; REQ-011.**
6. WHEN the cutoff of a pending task's deadline is reached THEN the server SHALL regard that task as overdue under the deadline semantics. **PCE-33; REQ-011.**
7. WHEN the server restarts after confirming a creation or pending-task edit as persisted THEN the server SHALL retain that accepted task state. **PCE-34; REQ-010.**
8. WHEN the server restarts after initial configuration THEN the server SHALL retain the configured product time zone. **PCE-35; REQ-028.**
9. WHEN persisted tasks are requested after closing and reopening the desktop THEN the server SHALL make their persisted state available. **PCE-36; REQ-010.**
10. WHEN the cutoff midnight occurs twice because of a product-zone transition THEN the server SHALL use its first occurrence. **PCE-49; REQ-011.**
11. WHEN the cutoff midnight does not exist because of a product-zone transition THEN the server SHALL use the first valid instant at or after that nominal calendar boundary, including after the following date if that entire date is skipped. **PCE-50; REQ-011.**

### Recover original operation results without duplicate application

1. The server SHALL confirm an operation as successful only after the requested change has been persisted. **PCE-37; REQ-010, REQ-031.**
2. WHEN the result of an original operation is consulted and the server has established its outcome THEN the server SHALL return that operation's outcome. **PCE-38; REQ-031.**
3. WHEN the same operation attempt is repeated THEN the server SHALL prevent duplicate application of that operation. **PCE-39; REQ-031.**
4. WHEN a creation or edit was persisted but its response was lost THEN the server SHALL make the original persisted outcome available on result consultation. **PCE-40; REQ-010, REQ-031.**
5. WHEN the original result is a uniqueness rejection THEN the server SHALL return that rejection when its result is consulted. **PCE-41; REQ-029, REQ-031.**
6. IF a different operation requests a different task that conflicts under uniqueness rules THEN the server SHALL reject the conflict rather than report success from the earlier task's operation. **PCE-42; REQ-029, REQ-031.**
7. The server SHALL keep rejection distinguishable from the absence of an established operation outcome. **PCE-43; REQ-031.**

### Serve the private personal collection within approved constraints

1. The Task Analyzer Server SHALL use Python 3.13 or later. **PCE-44; REQ-003.**
2. The Task Analyzer Server SHALL support dedicated self-hosting. **PCE-45; REQ-003.**
3. The Task Analyzer Server SHALL serve one person's collection without product accounts or product authentication. **PCE-46; REQ-027.**
4. The Task Analyzer Server SHALL use private access through Tailscale. **PCE-47; REQ-027.**

## Edge cases

The following are verification obligations linked to existing criteria, not additional product capabilities.

| Case | Required evidence / owner |
| --- | --- |
| Blank input and exact bounds | PCE-02 through PCE-06 and PCE-15; preserve the approved 200/201 and 5,000/5,001 input/expectation pairs. |
| Space normalization versus task identity | PCE-12, PCE-17, PCE-18, PCE-23; equivalence for comparison must not turn a title into an identity. |
| Partial edit with invalid data or conflict | PCE-15 and PCE-27; compare the entire persisted task before and after rejection. |
| Competing conflicting creations or edits | PCE-19, PCE-20, PCE-27; every accepted resulting state must respect uniqueness. No new edit-arbitration policy is selected here. |
| Lost response or overlapping repeated attempts | PCE-37 through PCE-43; inspect persisted state and original outcome, not merely response receipt. |
| Cutoff boundary | PCE-32/33; preserve the September 14/September 15, 00:00 example without a grace period. |
| Existing completed or deleted comparison candidates | PCE-19, PCE-24, PCE-25; use isolated fixtures for 1A and real lifecycle transitions in 1B. |
| Completing an undated task frees its title; completing a dated task does not free its title/date combination | Preserve both approved REQ-029 transition scenarios in 1B. |
| Reopening conflict and deletion effects | Preserve REQ-029's rejected-reopening example and deletion exclusion scenario in 1B; metric effects remain with REQ-025 analysis verification. |
| New Complete on completed / new Reopen on pending | Interview-approved rejection, allocated to 1B under REQ-008/028/031. Repetition of the original attempt still follows REQ-031. |

## Temporal clarifications

- TIME-02: a `2011-12-29` deadline in `Pacific/Apia` expires at `2011-12-30T10:00:00Z`, the first existing instant after the skipped following date.
- TIME-03: accept `0001-01-01` through `9999-12-30`; reject `9999-12-31` with durable `INVALID_DEADLINE` validation. No year-10000 sentinel is used.
- These decisions preserve the September 14/15 boundary and first-occurrence rule for repeated midnight.

## Verification and dependencies

Test modules carry REQ/PCE mappings. Preserve the title examples `Read notes` / ` READ  NOTES ` and `Review r?sum?` / `Review resume`, the 200/201 and 5,000/5,001 bounds, whole-state preservation on rejection, and restart/replay scenarios. Completed/deleted rows are isolated comparison fixtures, not 1B commands.

Dependent features reuse task identity, operation results, fixed-zone and deadline contracts. Original 31-task planning and approval history remain in Git at `8c68d6a`; the active workflow is defined in [AGENTS](../../../AGENTS.md). No requirement is marked fully Verified until its applicable external checks pass.

## Open questions

No behavioral question remains for 1A. Actual Ubuntu interpreter and private-access evidence are pending. Windows client technology and later feature contracts are decided in their own scope.

# Persistent Task Creation and Editing Specification

**Delivery:** 1A of the server lifecycle group.  
**Phase:** Specify, Design and Tasks approved on 2026-09-13, including the audit-time temporal clarifications and the audit revision. Execute is authorized for local implementation and local commits.

**Status:** Behavioral specification approved by the user. The delivery boundary was confirmed on 2026-09-13.

**TLC size:** Large. Validation, uniqueness, persistence, time, and operation outcomes interact across this delivery. Their technical decisions require Design after specification approval. No implementation tasks are authorized by this document.

## Problem Statement

The user needs the server to retain newly created tasks and edits reliably, including when a response is lost. This first delivery establishes creation and editing of pending tasks with validation, authoritative time, uniqueness, and recoverable operation outcomes. Delivery 1B extends those guarantees to completion, completed-task observations, reopening, and deletion.

Approved inputs: [requirements](../../../docs/product/requirements.md), [scope](../../../docs/product/scope.md), [MVP map](../../../docs/product/mvp-map.md), [domain vocabulary](../../../docs/product/domain.md), and [user flows](../../../docs/product/user-flows.md). [AGENTS.md](../../../AGENTS.md) governs authorization, traceability, and verification.

## Goals

- [ ] Accept valid creation and pending-task edits while rejecting invalid or conflicting changes without modifying persisted tasks.
- [ ] Preserve accepted task state, original creation time, and the fixed product time zone across server restarts.
- [ ] Confirm success only after persistence and recover the original operation result without applying the same attempt twice.
- [ ] Establish behavioral inputs for delivery 1B and deadline analysis without selecting storage, transport, or client technologies.

## Scope and Dependencies

The server owns the criteria below. The desktop will collect input, submit actions, and present results under separate specifications. Server verification can supply requests and inspect results without a desktop implementation; it does not complete the product's desktop or integrated acceptance scenarios.

The product has one person's collection and no product accounts. The server receives the product time zone from the desktop during initial configuration and retains it. Time-dependent scenarios use a configured zone. How configuration and task requests are exchanged belongs in Design.

Task identity is distinct from the title. Editing a title must continue to address the same task. This specification does not choose an identifier format or a physical data model.

| Delivery / capability | Dependency and allocation |
| --- | --- |
| 1A: this specification | No prior feature specification. Establishes creation, pending-task editing, time reference, persistence, and operation-result behavior. |
| 1B: lifecycle transitions and deletion | Depends on 1A's task identity, validation, uniqueness, time, persistence, and operation-result contracts. Adds completion, completed-task observation edits, reopening, and deletion. |
| Server deadline emphasis | Uses task status, deadline, product date, and cutoff semantics. Owns REQ-026 and the server contribution to REQ-034. Completed-task emphasis also depends on 1B. |
| Server productivity analysis | Uses original creation, latest completion, current status, deletion treatment, and deadline cutoff from 1A/1B. Owns calculations under REQ-021 through REQ-025 and server values needed by REQ-033. |
| Desktop task interaction and dashboard | Depend on the corresponding server contracts. Own input, commands, feedback, presentation, refresh interaction, and Windows validation. |

Dependencies concern stable contracts; they do not require finishing implementation before specifying a dependent feature. Deadline emphasis and productivity analysis can proceed independently once their required contracts are stable. Shared technical decisions are established in the first relevant Design and reused by dependent features.

## Out of Scope

| Feature | Reason / owner |
| --- | --- |
| Completion, editing completed-task observations, reopening, and deletion | Delivery 1B. Includes REQ-009, transition-specific portions of REQ-008/028/029/031, and lifecycle effects needed by REQ-025/030. |
| Deadline emphasis categories and refresh orchestration | Server deadline-emphasis and desktop specifications, REQ-026/034. This delivery defines the date/cutoff semantics, not emphasis presentation. |
| Metrics, chart populations, calculations, and formatting | Productivity-analysis and dashboard specifications, REQ-021 through REQ-025 and REQ-033. |
| Desktop UI and integrated Windows validation | Separate desktop specifications. Includes initial-zone collection UI, Save/Complete/Reopen/Delete controls, deletion confirmation, progress, the 15-second unconfirmed-result message, Retry sequencing, temporary input, and REQ-035. |
| Frameworks, storage mechanisms and schemas, transport, attempt identifiers, deployment tooling, and additional libraries | Technical choices reserved for Design. Python 3.13+ and Tailscale remain approved constraints. |
| Product accounts, offline operation, persistent local drafts, synchronization, backup, multiple-machine use, and other backlog capabilities | Outside the approved MVP scope. No backlog item is a requirement of this delivery. |

## Assumptions & Open Questions

| Assumption / decision | Chosen default | Rationale | Confirmed? |
| --- | --- | --- | --- |
| Split the first server group | Two deliveries: creation/pending-task editing first; transitions/completed-task observations/deletion second. | User selected two deliveries in interview Q1 and confirmed the resulting allocation. | Yes, 2026-09-13. |
| Operation guarantees in the split | Each delivery includes persistence confirmation, result lookup, and safe repetition for its own operations. | Splitting the lifecycle must not leave the first delivery without REQ-010/031 guarantees. | Yes, confirmed delivery boundary. |
| New incompatible-state commands in 1B | Reject a new Complete on an already completed task or a new Reopen on an already pending task, preserving data and timestamps. | User selected rejection in Q2. This differs from recovering the result of the same original attempt. | Yes, 2026-09-13; allocated to 1B. |
| Product semantics | Use the linked approved requirements and scenarios without changing their inputs, expected outcomes, or meaning. | Product discovery is complete; this specification allocates existing behavior. | Yes, approved product inputs. |
| Technical choices | Reserve choices and detailed contracts for Design; retain the approved Python baseline and Tailscale. | Required by the repository's current phase and the confirmed interview boundary. | Yes, approved project constraints. |
| Runtime baseline (PCE-44) | Require Python 3.13 or later instead of 3.11. | The user explicitly raised the minimum during task planning; REQ-003 and PCE-44 were updated together and no other criterion changed. | Yes, 2026-09-13. |
| Character counting (TXT-01) | Count user-perceived characters for title and observation bounds, not Unicode code points. | User explicitly selected visual character counting when the wire contract was detailed. | Yes, clarified during Design on 2026-09-13. |
| Exceptional midnight (TIME-01) | Use the first occurrence of a repeated cutoff midnight; if absent, use the first valid instant of the following date, extended for a wholly skipped date by TIME-02 below. | User explicitly approved this interpretation of REQ-011's calendar cutoff. | Yes, clarified during Design on 2026-09-13. |
| Skipped following date (TIME-02) | Use the first existing instant after the skipped date. | User approved the Pacific/Apia example during audit correction; see [context.md](context.md). | Yes, 2026-09-13. |
| Deadline range (TIME-03) | Accept calendar deadlines from `0001-01-01` through `9999-12-30`, inclusive. | User approved excluding `9999-12-31` so next-day cutoffs remain representable; no other original scenario changes. | Yes, 2026-09-13. |

**Open questions: none for the behavioral scope of delivery 1A.** Technical questions remain explicitly deferred in the final Open questions section. No unconfirmed behavioral defaults are adopted. The lesson script returned no confirmed lessons on 2026-09-13.

## User Stories

All stories below are P1/MVP. `PCE-NN` identifies a feature-local acceptance criterion; its attached `REQ-NNN` IDs retain product traceability. An accepted request in a scenario satisfies all other applicable validation and uniqueness rules.

### P1: Create a valid pending task

**User Story:** As the personal user, I want the server to accept valid tasks so that I can retain work with only a title or with optional details and a deadline.

**Why P1:** Creation is the first operation in the persistent task lifecycle.

**Acceptance Criteria:**

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

**Independent Test:** Against an isolated server test setup, submit a title-only task; titles at 200 and 201 characters after trimming; empty and whitespace-only titles; observations at 5,000 and 5,001 characters; multiline observations; and absent, valid past, and invalid calendar-date deadlines. Inspect the returned outcomes and persisted task values. No desktop is needed to verify these server rules. Add visual-character cases at the same limits: each letter plus combining marks and each combined emoji counts as one character. Preserve the original boundary cases and their expected outcomes.

### P1: Edit a pending task without losing its identity or valid state

**User Story:** As the personal user, I want to change a pending task's content while preserving the task and its original creation time.

**Why P1:** Editing must preserve the history on which later completion measurements depend.

**Acceptance Criteria:**

1. WHEN a valid edit to a pending task is applied THEN the server SHALL persist the requested title, observations, and deadline values. **PCE-11; REQ-007, REQ-008, REQ-010.**
2. WHEN a pending task is edited THEN the server SHALL preserve its task identity. **PCE-12; REQ-008, REQ-029.**
3. WHEN a pending task is edited THEN the server SHALL preserve its original creation time. **PCE-13; REQ-028.**
4. WHEN a content edit to a pending task is applied THEN the server SHALL retain pending status. **PCE-14; REQ-007, REQ-008.**
5. IF an edit violates task validation THEN the server SHALL reject it without changing the task's persisted state. **PCE-15; REQ-007, REQ-008.**
6. WHEN a valid edit removes optional observations or the optional deadline THEN the server SHALL persist the absence of the removed value. **PCE-16; REQ-007, REQ-008, REQ-010.**

**Independent Test:** Create a pending task, edit each editable field, and remove optional values. Compare identity, original creation time, status, and content before and after each edit. Repeat the creation story's applicable field-boundary cases as edits; rejected edits must leave the entire persisted task unchanged.

### P1: Enforce task uniqueness on creation and pending-task editing

**User Story:** As the personal user, I want conflicting tasks rejected while permitted tasks with similar titles can coexist.

**Why P1:** Uniqueness is an invariant of every accepted resulting task state, including the states later supplied by 1B.

**Acceptance Criteria:**

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

**Independent Test:** Exercise the rules with `Read notes` and ` READ  NOTES ` as equivalent titles and `Review résumé` and `Review resume` as different titles. Cover same dates, different dates, dated versus undated tasks, self-exclusion, and pending/completed/deleted comparison populations. Isolated fixtures may represent completed or deleted tasks for these comparison tests; they do not add completion or deletion commands to 1A. Creating those states through real transitions and checking their effects remains part of 1B's scenarios.

### P1: Retain authoritative task state and product time

**User Story:** As the personal user, I want saved tasks and deadline interpretation to survive restarts and remain independent of later desktop clock changes.

**Why P1:** Durable task history and one time reference are prerequisites for subsequent lifecycle and analysis features.

**Acceptance Criteria:**

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

**Independent Test:** Set a known initial product zone, create and edit a task, and compare task state and configured zone across a server restart and a fresh client session. Vary the client's clock and zone while keeping the server reference controlled. Preserve the approved September 14 deadline example: valid throughout September 14; overdue at September 15, 00:00 in the product zone. Add repeated-midnight and missing-midnight fixtures with independently established expected instants, including the skipped `2011-12-30` date in `Pacific/Apia`: a December 29 deadline expires at `2011-12-30T10:00:00Z`. Test both supported date endpoints with UTC and positive/negative-offset zones, and rejection of `9999-12-31` on creation and editing. This checks cutoff semantics, not emphasis categories or UI refresh. The companion completion-at-cutoff scenario belongs to 1B and analysis coverage.

### P1: Recover original operation results without duplicate application

**User Story:** As the personal user, I want to establish whether a save was persisted after losing a response, without creating another task or applying an edit again.

**Why P1:** Creation and editing are not reliable if an unknown client outcome can cause duplicate application.

**Acceptance Criteria:**

1. The server SHALL confirm an operation as successful only after the requested change has been persisted. **PCE-37; REQ-010, REQ-031.**
2. WHEN the result of an original operation is consulted and the server has established its outcome THEN the server SHALL return that operation's outcome. **PCE-38; REQ-031.**
3. WHEN the same operation attempt is repeated THEN the server SHALL prevent duplicate application of that operation. **PCE-39; REQ-031.**
4. WHEN a creation or edit was persisted but its response was lost THEN the server SHALL make the original persisted outcome available on result consultation. **PCE-40; REQ-010, REQ-031.**
5. WHEN the original result is a uniqueness rejection THEN the server SHALL return that rejection when its result is consulted. **PCE-41; REQ-029, REQ-031.**
6. IF a different operation requests a different task that conflicts under uniqueness rules THEN the server SHALL reject the conflict rather than report success from the earlier task's operation. **PCE-42; REQ-029, REQ-031.**
7. The server SHALL keep rejection distinguishable from the absence of an established operation outcome. **PCE-43; REQ-031.**

**Independent Test:** Persist a creation, suppress its response, consult the original result, and repeat the same attempt. Verify the original success, exactly one task, and unchanged original creation time. Repeat for an edit and check that it is not applied again, including after a subsequent accepted edit. Verify an original rejection remains the consulted rejection and a different conflicting creation is rejected under uniqueness. Exercise overlapping repetitions of one attempt and distinct conflicting attempts: one operation must not apply twice, and conflicting resulting tasks must not both be accepted. Result lookup and attempt recognition must remain consistent with task durability across restart; Design defines their technical contract and persistence approach.

The desktop's 15-second deadline is feedback timing, not a server cancellation, rejection, rollback, or processing-time guarantee. Retry-first lookup, progress, repeated-submission controls, and the user-visible unconfirmed state remain desktop criteria. Unknown outcomes must not be treated as proof that no change persisted.

### P1: Serve the private personal collection within approved constraints

**User Story:** As the personal user, I want a dedicated server for my collection without a product sign-in flow.

**Why P1:** The first server delivery must conform to the existing platform and access boundary.

**Acceptance Criteria:**

1. The Task Analyzer Server SHALL use Python 3.13 or later. **PCE-44; REQ-003.**
2. The Task Analyzer Server SHALL support dedicated self-hosting. **PCE-45; REQ-003.**
3. The Task Analyzer Server SHALL serve one person's collection without product accounts or product authentication. **PCE-46; REQ-027.**
4. The Task Analyzer Server SHALL use private access through Tailscale. **PCE-47; REQ-027.**

**Independent Test:** During future Design, review runtime and deployment support against REQ-003/027. During authorized implementation verification, check the configured Python baseline and private personal-access path without a product sign-in. This Specify document does not authorize deployment or network configuration changes; the desktop portion of the access scenario remains pending.

## Edge Cases

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

## Implicit-Requirement Dimensions

| Dimension | Resolution within this delivery |
| --- | --- |
| Input validation and bounds | PCE-01 through PCE-10, PCE-15/16; approved limits and optional calendar-date semantics. |
| Failure and partial failure | PCE-15, PCE-27, PCE-34, PCE-37 through PCE-43; rejection preserves state, while missing confirmation does not establish rollback. |
| Idempotency, retry, and duplicates | PCE-17 through PCE-27 and PCE-38 through PCE-43; task uniqueness and repetition of one attempt remain distinct. |
| Authentication boundaries and rate limits | PCE-46/47 define the approved boundary. Rate limiting is N/A as a product requirement: none is approved for this personal MVP. |
| Concurrency and ordering | Uniqueness and no duplicate application hold for overlapping attempts. Enforcement and request/result ordering contracts belong in Design; no collaborative editing or multiple-machine capability is added. |
| Data lifecycle and expiry | PCE-13, PCE-28 through PCE-36, and PCE-37 through PCE-40 establish durability. Task deletion commands belong to 1B. Archival and task expiry are N/A because neither is an MVP capability. Result-retention mechanisms belong in Design and must preserve approved retry behavior. |
| Observability | No additional user-facing observability requirement. Future implementation follows AGENTS.md's standard logging requirement; its schema remains a Design question. |
| External-dependency failure | Loss of server communication is addressed by the operation-outcome boundary and desktop-owned REQ-031/032. Additional external service integrations are N/A because none are in this delivery. |
| State-transition integrity | PCE-01, PCE-14/15, and PCE-27 cover creation into pending and edits preserving valid state. Completion, reopening, and deletion are assigned to 1B. |

## Requirement Traceability

| Requirement ID | Acceptance criteria / story | Coverage in 1A and remaining allocation | Phase | Status |
| --- | --- | --- | --- | --- |
| REQ-003 | PCE-44, PCE-45 | Server runtime/self-hosting constraints. Design baseline approved; audit revision and implementation verification pending. | Execute | In Execute |
| REQ-007 | PCE-01 through PCE-10, PCE-11, PCE-14 through PCE-16, PCE-48, PCE-51, PCE-52 | Task fields, visual-character bounds, pending creation, and pending edits. Completed-task behavior belongs to 1B; input UI belongs to desktop. | Execute | In Execute |
| REQ-008 | PCE-01, PCE-11, PCE-12, PCE-14 through PCE-16, PCE-27, PCE-52 | Creation and pending edits only. Remaining lifecycle operations belong to 1B; end-to-end actions require desktop. | Execute | In Execute |
| REQ-010 | PCE-07, PCE-11, PCE-16, PCE-34, PCE-36, PCE-37, PCE-40 | Durability of this delivery's operations. Extend to 1B operations and verify desktop confirmation separately. | Execute | In Execute |
| REQ-011 | PCE-08, PCE-32, PCE-33, PCE-49, PCE-50 | Calendar-date cutoff, exceptional midnight, and pending overdue semantics. Completion-at-cutoff and presentation are verified in dependent features. | Execute | In Execute |
| REQ-028 | PCE-13, PCE-28 through PCE-31, PCE-35 | Original creation, server time, and retained fixed zone. Completion timestamps belong to 1B; initial-zone collection UI belongs to desktop. | Execute | In Execute |
| REQ-029 | PCE-12, PCE-17 through PCE-27, PCE-41, PCE-42 | Creation/edit comparison rules include completed/deleted candidates. Actual completion/reopening/deletion transition scenarios belong to 1B. | Execute | In Execute |
| REQ-031 | PCE-26, PCE-37 through PCE-43 | Server outcomes, lookup, and safe repetition for creation/edit. 1B extends operation coverage; desktop owns progress, 15 seconds, Retry sequencing, and presentation. | Execute | In Execute |
| REQ-027 | PCE-46, PCE-47 | Server personal/private-access constraints. Design defines detailed setup; actual private-access evidence and the desktop scenario remain pending. | Tasks | In Tasks |

**Coverage:** 9 active product IDs mapped to 52 acceptance criteria. All existing IDs and protected scenario inputs/outcomes are retained. PCE-08/09 and PCE-50 now reflect the audit clarifications explicitly approved by the user; PCE-51/52 add deadline-range criteria. PCE-48/49 preserve the earlier visual-counting and repeated-midnight clarifications. No requirement is marked Verified. The formal [task plan](tasks.md) is approved and Execute is authorized; no application code or executable tests exist yet at the time of this record. Every acceptance criterion must acquire requirement-derived tests and evidence during the authorized Tasks/Execute work; the Independent Test descriptions above are planned scenarios, not test results.

The remaining active MVP requirements are allocated outside 1A: REQ-009 to 1B; REQ-021 through REQ-025 and REQ-033 to analysis/dashboard; REQ-026 to deadline emphasis/presentation; REQ-001, REQ-030, REQ-032, and REQ-035 to desktop work, with deletion's server effects in 1B; and REQ-034 to derived-result and desktop refresh work. Cross-feature scenarios must retain their original product IDs and expectations.

## Success Criteria

- [ ] Every 1A acceptance criterion has passing requirement-derived verification under the approved implementation design and tasks.
- [ ] Rejected invalid/conflicting edits leave persisted task state unchanged.
- [ ] Accepted creation and edits remain available after server restart and a fresh client session.
- [ ] Lost responses and repeated attempts recover the original result without duplicate application.
- [ ] Product-zone and cutoff scenarios preserve the approved boundary values.
- [ ] Traceability clearly distinguishes 1A server evidence from 1B and desktop coverage still required to complete the MVP.

These are future completion conditions. The behavioral specification is approved; implementation and verification remain pending.

## Open questions

No unresolved behavioral decision remains for 1A after the user-approved [temporal clarifications](context.md). The [Design](design.md) records the approved stack, baseline contracts and approved audit revision; technical questions already resolved there are not reopened here.

- **Resolved 2026-09-13:** the user approved the audit amendments to dependencies, protocol serialization, runtime startup, package verification and bootstrap gates, together with the revised [tasks](tasks.md). Implementation proceeds under that plan.
- Confirm the actual target interpreter, paths and private-access values in an explicitly authorized deployment session. Local task completion cannot satisfy that external verification checkpoint.
- Windows client technology and remaining 1B/analysis/desktop decisions belong to their respective designs.

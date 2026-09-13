# Development instructions

## Project phase and language

- The product definition in `docs/product/` is consolidated. Delivery 1A has an approved behavioral specification and is in Design. Do not restart product definition or write application code before the required Design and Tasks approvals.
- All repository artifacts must be in English: code, comments, documentation, and folder and file names. A request written in another language does not change this rule.
- Python 3.13+, FastAPI, SQLite on the dedicated Ubuntu Server 26.04.1 LTS host, and private Tailscale access are approved; see [AD-001](.specs/STATE.md#ad-001) and the raised runtime baseline in [AD-003](.specs/STATE.md#ad-003). Other technical choices require approval in the relevant Design. Record unresolved choices as options under "Open questions" rather than treating draft proposals as approved.
- Treat every item under "Backlog" as future work outside the MVP, never as an MVP requirement. Moving an item into scope requires explicit approval.

## Source of truth and workflow

This project uses the `tlc-spec-driven` skill by [Tech Leads Club](https://github.com/tech-leads-club/agent-skills). [Product requirements](docs/product/requirements.md) remain the approved product inputs. Approved feature specifications under `.specs/features/` are the source of truth for implementation. Preserve active `REQ-NNN` IDs and trace feature criteria, tasks, and tests to them; feature-local IDs may supplement, but must not replace, product IDs.

Read documentation on demand: use [README.md](README.md) and [MVP scope](docs/product/scope.md) for orientation. Activate `tlc-spec-driven` for feature work; its repository bundle is [.ai/skills/tlc-spec-driven/SKILL.md](.ai/skills/tlc-spec-driven/SKILL.md). Read its applicable references completely. Resolve references and scripts relative to the active skill's `SKILL.md`, not the repository root.

On resume, read [STATE.md](.specs/STATE.md), reconcile its Handoff with the current branch, `git status --porcelain`, recent commits, and any existing task status, then state the next authorized step. For a feature, read the relevant product requirements, then its `spec.md`, `context.md` if present, `design.md` if present, and `tasks.md` if present. For a Small change with an inline specification, read that approved specification instead.

Follow **Specify → Design → Tasks → Execute**, with depth determined by TLC's sizing:

| Size | Scope | Specification and design | Task planning |
| --- | --- | --- | --- |
| Small | At most 3 files, describable in one sentence | Inline one-line specification; skip Design when straightforward. | Inline atomic steps; skip formal Tasks when at most 3 obvious steps. |
| Medium | Clear feature with fewer than 10 tasks | Brief `spec.md`; inline design when no architectural decision is needed. | Implicit tasks only when the skip rules below hold. |
| Large | Feature spanning multiple components | Full `spec.md` with traceable IDs and `design.md` covering architecture and contracts. | `tasks.md` with atomic tasks, dependencies, and execution phases. |
| Complex | Ambiguity or a new domain | Full specification; discuss relevant gray areas within Specify; research and design. | Full task breakdown and execution phases; interactive UAT within Execute when user-facing behavior is complex. |

Specify and Execute are required for an authorized change. Design may be skipped only when there are no architectural decisions, new patterns, or component interactions to resolve. Tasks may be skipped only for at most 3 obvious steps. Execute always begins by listing atomic steps inline; if that reveals more than 5 steps or complex dependencies, create and approve a formal `tasks.md` before implementation. The execution plan belongs in `tasks.md` when formal Tasks applies.

Obtain behavioral specification approval before Design. Resolve and approve relevant technical choices and contracts in Design before Tasks and Execute; establish shared decisions in the first relevant design and reuse them in dependent features. Obtain task approval before executing formal tasks; inline work must also have an approved scope. Reduced artifact depth never waives approval, authorization, traceability, testing, or verification.

- Do not assume behavior absent from the specification or business contract. Clarify ambiguity before implementing the affected behavior.
- Obtain approval before changing behavior, scope, or acceptance criteria. Wording corrections that preserve meaning may proceed without a new approval.
- Use existing product decisions to answer TLC clarification prompts. Skill examples, story priorities, assumption defaults, and lessons do not authorize new behavior, backlog scope, or technology choices.
- Implement and verify approved tasks autonomously within their authorized scope.
- Every implementation change must be traceable to an approved requirement. Every requirement and acceptance criterion must have corresponding tests before implementation is considered complete.
- Do not modify unrelated functionality.

## TLC artifacts and memory

- `.specs/` is the TLC artifact root; `.specs/features/` holds future feature directories. Create each artifact only when its phase produces substantive content. Do not create empty feature specifications, `context.md`, `design.md`, `tasks.md`, or `validation.md`. The `.gitkeep` in `features/` only preserves the directory in Git.
- `.specs/STATE.md` holds `Decisions` and `Handoff`. Keep approved product definitions in `docs/product/` and link to them. Record only qualifying project-level decisions as append-only `AD-NNN` entries; update a superseded entry's status without deleting it. Replace only the Handoff section when recording session state; never overwrite the Decisions log during handoff updates.
- `.specs/lessons.json` is canonical machine state and `.specs/LESSONS.md` is its rendered view. Only the installed skill's `scripts/lessons.py` may create or update them. An empty store is valid; record lessons only from grounded verification signals. Load confirmed lessons at Specify and Design; candidates and quarantined lessons are not guidance.
- Use `context.md` only for actual gray-area decisions within Specify. Use `validation.md` for the independent Verifier's completed report, with a verdict and evidence.
- Keep `AGENTS.md`, `README.md`, product documents, and manually maintained project state ending with `Open questions`. Script-managed lesson files retain the tool's generated format.

Future feature artifacts follow the applicable TLC templates and record unresolved decisions where those templates require them. Do not create artifacts to make an inapplicable validator pass.

## Branches and authorization

- Work on dedicated branches named `docs/<topic>`, `feat/<topic>`, or `fix/<topic>` according to the work's purpose.
- Follow TLC's commit standard: one atomic Conventional Commit per completed task, created without asking for a further approval. Mark the task complete in `tasks.md` and update traceability before that commit, and include those updates in the same commit. Never batch several tasks into one commit, and never commit work whose gate has not passed.
- Task approval authorizes local implementation and its per-task commits on the work branch. Validate each message with TLC's `check_commit.py`. Verification still runs on uncommitted work when a task is interrupted.
- Installing or configuring TLC authorizes no application implementation, push, merge, releases, deployment, or database changes. Preserve outstanding work in place unless the user authorizes another action.
- Obtain explicit authorization before pushing, merging, publishing releases, deploying, or performing destructive operations that discard work or data.
- Do not introduce unauthorized external libraries.
- Do not change public function signatures, including names and parameters, without authorization.
- An approved specification explicitly naming a dependency or public signature change authorizes that named change. Approval does not extend to unrelated changes.
- Authorization already given for a specific action remains sufficient; do not repeatedly request the same approval.

## Architecture and code quality

- Follow the approved folder and file architecture. Do not alter its layout without approval; add implementation files only as permitted by approved tasks and design.
- Apply SOLID, Clean Code, SRP, DRY, and KISS with practical judgment. Keep functions small, cohesive, and focused on one purpose; prefer early returns when they improve readability.
- Reuse existing code, components, utilities, and established patterns before creating new ones.
- Avoid overengineering and premature abstractions.
- Use descriptive variable and function names. Code must be readable and maintainable.
- Do not introduce duplicate or unnecessary code.
- Handle specific exceptions with clear error messages.
- Deliver complete, tested implementation for the approved scope, with appropriate types and documentation. Do not present pseudocode, stubs, or unfinished code as completed implementation.

For server-side Python:

- Require Python 3.13 or later.
- Use type annotations for all functions and methods, including parameters and return values.
- Follow PEP 8 and clean-code principles.
- Document modules, classes, functions, and methods using Google-style docstrings, including parameter documentation where applicable.
- Produce structured logs through the standard `logging` module. The specific log schema remains open.

Client language conventions and formatting tools must be defined after the client technology is selected.

## Persistence and database safeguards

- Server persistence is part of the MVP and must follow approved specifications. Persistent local drafts and cloud backup remain outside the MVP, as defined by [Scope](docs/product/scope.md#mvp-boundaries).
- Do not introduce or change storage mechanisms, schemas, or data destinations without approval.
- Do not directly modify development or production databases without explicit authorization. This includes running migrations and changing database records or schema.
- Approval to implement persistence code does not itself authorize applying database changes.
- Automated tests may create and modify a test database only when the test configuration clearly identifies it as isolated and disposable. Do not assume an unknown database is safe for testing.

## Tests and verification

Tests are mandatory for acceptance criteria. Do not deliver new feature code without corresponding tests.

- Trace tests to the affected requirements and acceptance criteria.
- Features and bug fixes must include corresponding tests; refactors must preserve behavior and pass relevant regression tests. Add tests where the affected behavior lacks coverage. Merely recommending tests is not sufficient.
- Protect provided test scenarios: do not alter their inputs, expected outcomes, or behavioral meaning without explicit authorization.
- Never weaken, remove, or adapt scenarios merely to make an implementation pass.
- TLC adequacy reviews and deviation markers do not authorize removing protected scenarios or changing approved behavior.
- Adding tests and maintaining test infrastructure is allowed when protected scenarios retain their meaning.
- Before marking implementation complete, run the relevant requirement tests, regression tests, and configured formatting, linting, and build checks.
- For documentation changes, check consistency with approved decisions, links, scope boundaries, and the required document structure.
- Before marking a Windows UI change complete, validate layout and usability across the window sizes and display-scaling settings defined by its approved acceptance criteria. Check for clipped content, overlapping elements, and inaccessible controls. Define the validation range before implementation; this rule does not add web or mobile support to the MVP.
- Report what changed, how it was verified, and any material limitations. Distinguish checks actually run from checks pending or unavailable; do not claim unperformed verification.

For future feature work, follow TLC's deterministic gates with a Python interpreter and the scripts from the resolved skill directory:

| Script | When it applies |
| --- | --- |
| `validate_spec.py <spec-path-or-feature>` | Before presenting an existing formal specification for approval; check required sections, EARS criteria, assumptions, and IDs. |
| `validate_tasks.py <tasks-path-or-feature>` | Before formal task approval and again before Execute when `tasks.md` exists. |
| `check_commit.py --message "<message>"` | Validate each task's Conventional Commit message before committing it. |
| `validate_state.py <feature>` | Before declaring a feature complete; checks the Verifier's PASS report and evidence. This does not validate `STATE.md`. |

Run from the project root or pass the script's documented `--root` option. Fix nonzero gate results before proceeding. These scripts check structure; they do not replace requirement tests or semantic review. With no feature artifacts, report feature gates as not yet applicable.

Formal `tasks.md` must include the Test Coverage Matrix, Gate Check Commands, and per-task Tests and Gate fields, grounded in repository testing rules and approved tooling. Each implementation task includes its corresponding tests. After the final implementation task, run an independent Verifier with spec-derived outcomes and the discrimination sensor in isolated disposable copies of the actual changes, including uncommitted and untracked files, preserving the real working tree. Record per-criterion evidence and the actual reviewed diff in `validation.md`; resolve failures before marking the feature complete. Do not wait for a commit or request permission merely to run this verification.

## Open questions

This section owns future technical decisions for the MVP. [Requirements](docs/product/requirements.md) defines product behavior, including the Windows validation range. Questions about future capabilities and their technologies belong to the [Backlog](docs/product/backlog.md#open-questions). Resolve the relevant questions in each feature's design; no option below selects a technology.

- Which Windows client technology and remaining supporting libraries should be proposed for approval under the [platform and access constraints](docs/product/requirements.md#platform-and-access)? FastAPI, SQLite, and the Ubuntu server target are approved in [AD-001](.specs/STATE.md#ad-001); detailed proposals are in the [1A Design](.specs/features/persistent-task-creation-editing/design.md).
- Which communication contract should carry task operations and results: request/response communication, persistent communication, or a combination? How will it provide the required refresh behavior?
- How should the server recognize repeated operation attempts, expose their results, and enforce task uniqueness consistently? Define the technical contract and persistence approach without changing the required rejection and retry behavior.
- Which time representations and conversion approach should implement server timestamps and the fixed product time zone?
- Which deployment tooling and detailed Tailscale configuration should provide private access and desktop connection setup?
- Which test framework, formatter, linter, type checker, build commands, and CI checks should the project configure?
- What structured logging schema and fields should the server use?
- What concrete implementation folder and file architecture should future feature specifications define within the existing layout?

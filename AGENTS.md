# Development instructions

## Project phase and language

- The project is in product definition. Do not write application code during this phase.
- All repository artifacts must be in English: code, comments, documentation, and folder and file names. A request written in another language does not change this rule.
- Do not select an implementation stack during this phase. Python 3.11+ is selected for the server, and Tailscale is selected for private access. Other implementation stack choices remain open. Record necessary unresolved technical decisions as options under "Open questions" rather than selecting them.
- Treat every item under "Backlog" as future work outside the MVP, never as an MVP requirement. Moving an item into scope requires explicit approval.
- Every document created or updated for the initial documentation deliverables must end with an "Open questions" section listing unresolved decisions. If none remain, state that explicitly.

## Source of truth and workflow

This project follows Spec-Driven Development. Specifications under `/specs` are the source of truth for application behavior. [Product requirements](docs/product/requirements.md) provide the approved product inputs for that specification work.

Read documentation on demand: use [README.md](README.md) and [MVP scope](docs/product/scope.md) for orientation; for a specific task, read the relevant requirements and related specifications, following their links only as needed. Keep the feature-document reading order and workflow below.

Before implementing a feature, read its documents in this order:

1. `spec.md`
2. `design.md`
3. `plan.md`
4. `tasks.md`

Follow the workflow: specification, design, plan, tasks, implementation, tests, and verification. Every implementation change must be traceable to an approved requirement. Every requirement and acceptance criterion must have corresponding tests before implementation is considered complete.

Define product behavior in `spec.md`; resolve the relevant technical choices and contracts in `design.md` after the behavioral specification is approved, before planning and implementation. Establish shared technical decisions in the first relevant design and reuse them in dependent features.

- Do not assume behavior absent from the specification or business contract. Clarify ambiguity before implementing the affected behavior.
- Obtain approval before changing behavior, scope, or acceptance criteria. Wording corrections that preserve meaning may proceed without a new approval.
- Implement and verify approved tasks autonomously within their authorized scope.
- Do not modify unrelated functionality.

## Initial documentation checkpoints

Complete the initial documentation sequence in order, one artifact at a time:

1. `docs/product/`: present the file organization for approval, use `grill-me` to clarify content, then fill the approved files and obtain confirmation before proceeding.
2. `AGENTS.md`: use `grill-me` to clarify working rules, write the file, and obtain confirmation before proceeding.
3. `README.md`: include product description, MVP scope, exclusions from the MVP, current project status, and folder structure, followed by "Open questions."

These artifact checkpoints apply to this initial documentation sequence. Subsequent implementation and verification may proceed within approved tasks, subject to the explicit authorization rules below.

## Branches and authorization

- Work on dedicated branches named `docs/<topic>`, `feat/<topic>`, or `fix/<topic>` according to the work's purpose.
- Never commit unless the user explicitly requests it.
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

- Require Python 3.11 or later.
- Use type annotations for all functions and methods, including parameters and return values.
- Follow PEP 8 and clean-code principles.
- Document modules, classes, functions, and methods using Google-style docstrings, including parameter documentation where applicable.
- Produce structured logs through the standard `logging` module. The specific log schema remains open.

Client language conventions and formatting tools must be defined after the client technology is selected.

## Persistence and database safeguards

- Implement local persistence and cloud backup only as defined by approved specifications. The product requires persistence; it is not prohibited.
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
- Adding tests and maintaining test infrastructure is allowed when protected scenarios retain their meaning.
- Before marking implementation complete, run the relevant requirement tests, regression tests, and configured formatting, linting, and build checks.
- For documentation changes, check consistency with approved decisions, links, scope boundaries, and the required document structure.
- Before marking a Windows UI change complete, validate layout and usability across the window sizes and display-scaling settings defined by its approved acceptance criteria. Check for clipped content, overlapping elements, and inaccessible controls. Define the validation range before implementation; this rule does not add web or mobile support to the MVP.
- Report what changed, how it was verified, and any material limitations. Distinguish checks actually run from checks pending or unavailable; do not claim unperformed verification.

## Open questions

This section owns future technical decisions for the MVP. [Requirements](docs/product/requirements.md) defines product behavior, including the Windows validation range. Questions about future capabilities and their technologies belong to the [Backlog](docs/product/backlog.md#open-questions). Resolve the relevant questions in each feature's design; no option below selects a technology.

- Which Windows client technology, Python backend framework, server storage technologies, and supporting libraries should be proposed for approval under the [platform and access constraints](docs/product/requirements.md#platform-and-access)?
- Which communication contract should carry task operations and results: request/response communication, persistent communication, or a combination? How will it provide the required refresh behavior?
- How should the server recognize repeated operation attempts, expose their results, and enforce task uniqueness consistently? Define the technical contract and persistence approach without changing the required rejection and retry behavior.
- Which time representations and conversion approach should implement server timestamps and the fixed product time zone?
- Which deployment tooling and detailed Tailscale configuration should provide private access and desktop connection setup?
- Which test framework, formatter, linter, type checker, build commands, and CI checks should the project configure?
- What structured logging schema and fields should the server use?
- What concrete implementation folder and file architecture should future feature specifications define within the existing layout?

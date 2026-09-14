# Development instructions

## Project and scope

Task Analyzer is a personal learning and portfolio project. Prefer understandable code and a small development workflow. New features are paused during the approved simplification.

- All repository artifacts are in English.
- Python 3.13+, FastAPI, SQLite and private Tailscale access remain the approved stack. Use uv for dependencies and the local environment.
- [Requirements](docs/product/requirements.md) and [scope](docs/product/scope.md) define behavior. Backlog ideas, including a possible PostgreSQL migration, are not implementation requirements.
- Do not add architectural layers, frameworks or capabilities for hypothetical future needs.

## Source of truth and workflow

Use lightweight SDD inspired by TLC: specify the observable behavior, record necessary design decisions, implement small steps, and verify outcomes. This replaces mandatory execution of the bundled TLC skill. Its bundle remains optional study material; do not load it during routine work or generate its matrices, lessons or minimum test quotas.

Read on demand:

1. On resume, read this file and the Handoff in [.specs/STATE.md](.specs/STATE.md), then reconcile branch, status and recent commits.
2. For setup and navigation, use [README](README.md).
3. For a change, read only the affected requirements, feature specification and relevant contract sections. Do not load every product document or historical report.

Keep one concise specification per feature. Add a separate Design only for substantial technical contracts or decisions. Small changes use an inline scope and steps; larger changes use one short checklist, not repeated per-task templates. The user's approval of a concrete plan authorizes its implementation and local commits; do not request the same approval again.

Preserve REQ-NNN and PCE-NN identifiers and approved examples. Ask before changing behavior or adding scope; routine implementation choices within an approved plan need no additional approval. The current simplification, uv migration and audit fixes are approved in [maintenance](docs/maintenance.md).

## Code and tests

- Keep functions cohesive, typed and directly readable. Reuse helpers when there is actual repetition; avoid speculative abstractions.
- Write docstrings for non-obvious contracts and decisions. Do not restate function names, type annotations or the entire specification in code.
- Tests demonstrate behavior and failures. Preserve approved inputs, expected outcomes and regression scenarios; consolidate equivalent setup and use parametrization instead of repeated test bodies.
- There are no minimum test counts or line-count targets. Test domain boundaries, HTTP contracts and critical persistence/concurrency behavior at the layer that supplies useful evidence.
- Fix defects rather than weakening assertions or skipping failing scenarios.
- Run the affected tests during work and the README quality checks before delivery. Installed-package smoke tests must import the built wheel outside the checkout.
- Log through standard logging with the JSON schema in the feature Design. Never log task content or credentials.
- Report actual verification and remaining limitations. A passing local suite does not prove target-host compatibility or private access.

## State and repository changes

- Use dedicated docs/, feat/ or fix/ branches and atomic Conventional Commits for completed work. Preserve unrelated local changes.
- Keep [.specs/STATE.md](.specs/STATE.md) short: append significant shared decisions and replace only its Handoff when recording progress. Preserve decision history.
- Keep active documentation concise and current. Reference Git history for old plans/reports instead of copying them into new archives. Do not read generated locks, old lesson stores or skill references as routine context.
- Keep manually maintained project guidance ending with Open questions.
- No push, merge, deployment or destructive discard without explicit authorization.

## Database safeguards

- Never initialize, migrate or modify a real database without explicit authorization. Persistence code approval does not authorize applying it.
- Tests use new, explicitly disposable paths. Never fall back to an environment-configured database.
- Preserve the fixed product zone, task identity, original creation time, uniqueness rules and immutable operation results.

## Open questions

- Target Ubuntu interpreter, paths, tailnet hostname and authorized devices require a separate deployment session.
- Windows client technology and later feature contracts remain undecided.
- CI integration is not selected; local quality checks remain sufficient for development.

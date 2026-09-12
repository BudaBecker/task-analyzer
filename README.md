# Task Analyzer

## Product description

Task Analyzer is a personal task-management and analysis product composed of the **Desktop App** and the **Task Analyzer Server**. The server owns business rules, persistence, and productivity analysis. The Windows desktop provides simple interaction and presentation. See the [product vision](docs/product/vision.md) for the problem and intended outcomes.

## MVP scope

The MVP covers task management with optional deadlines, server validation and persistence, visual deadline emphasis, and a dedicated productivity dashboard. [Scope](docs/product/scope.md) defines the boundaries, component responsibilities, and completion criterion; [Requirements](docs/product/requirements.md) defines the behavioral rules and acceptance scenarios.

## Outside the MVP

Accounts, installation management, recovery, backup, synchronization, offline and multiple-machine operation, persistent local drafts, reminders/notifications, automatic priority, and priority-grouped metrics are outside the MVP. The [Backlog](docs/product/backlog.md) also contains broader desktop improvements, other clients, and integrations. Backlog items must not be used as requirements for MVP specifications or implementation.

## Current project status

The product definition is ready for feature specification work. The [MVP map](docs/product/mvp-map.md) prioritizes the server and identifies dependencies and opportunities for parallel work.

Application code, executable tests, and build/deployment configuration have not been implemented. Existing feature-specification files are empty scaffolding. There is no runnable application or setup procedure yet.

The [platform and access requirements](docs/product/requirements.md#platform-and-access) define the Windows target, server-side Python baseline, dedicated hosting, and private access. Other technical choices remain open in [AGENTS.md](AGENTS.md#open-questions).

Development follows Spec-Driven Development. Specifications under `specs/` are the source of truth for application behavior. [AGENTS.md](AGENTS.md#source-of-truth-and-workflow) defines the workflow: specify behavior, approve it, and then resolve the relevant technical choices in the design before planning and implementation.

## Documentation guide

| Document | Owns |
| --- | --- |
| [Vision](docs/product/vision.md) | Problem, intended outcomes, and product-value evaluation. |
| [Scope](docs/product/scope.md) | MVP boundary, component responsibilities, and completion criterion. |
| [Requirements](docs/product/requirements.md) | Numbered product behavior and acceptance scenarios. |
| [User flows](docs/product/user-flows.md) | User interaction sequences linked to requirements. |
| [Backlog](docs/product/backlog.md) | Future capabilities outside the MVP and their own questions. |
| [MVP map](docs/product/mvp-map.md) | Suggested feature-specification order, dependencies, and parallel work. |
| [Domain](docs/product/domain.md) | Shared vocabulary for MVP concepts. |
| [AGENTS.md](AGENTS.md) | Working rules, approval workflow, and future technical decisions. |

## Folder structure

The workspace uses the following structure. Empty scaffold directories may not appear in a Git checkout until files are added.

```text
task-analyzer/
|-- .ai/skills/                  # Local interview skills
|-- .vscode/                    # Local editor settings; ignored by Git
|-- docker/                     # Empty scaffold; no tooling decision implied
|-- docs/
|   |-- architecture/           # Empty architecture documentation scaffold
|   `-- product/
|       |-- vision.md
|       |-- scope.md
|       |-- requirements.md
|       |-- user-flows.md
|       |-- backlog.md
|       |-- mvp-map.md
|       `-- domain.md
|-- specs/
|   |-- 01-[SpecName]/           # Empty feature-specification scaffold
|   |   |-- spec.md
|   |   |-- design.md
|   |   |-- plan.md
|   |   `-- tasks.md
|   `-- 02-[SpecName]/           # Same four empty specification files
|-- src/
|   |-- desktop-app/            # Empty Desktop App source scaffold
|   `-- task-analyzer-server/   # Empty Task Analyzer Server source scaffold
|-- tests/                      # Empty test scaffold
|-- .gitignore
|-- AGENTS.md                   # Development and collaboration rules
|-- CLAUDE.md                   # Local reference to AGENTS.md; ignored by Git
`-- README.md
```

## Open questions

No unresolved MVP product-behavior decisions remain. [AGENTS.md](AGENTS.md#open-questions) owns the technical choices for future designs. [Vision](docs/product/vision.md#open-questions) owns the product-value evaluation question, and [Backlog](docs/product/backlog.md#open-questions) owns questions about future capabilities; neither adds requirements to the MVP.

# Task Analyzer

## Product description

Task Analyzer is a personal task-management and analysis product composed of the **Desktop App** and the **Task Analyzer Server**. The server owns business rules, persistence, and productivity analysis. The Windows desktop provides simple interaction and presentation. See the [product vision](docs/product/vision.md) for the problem and intended outcomes.

## MVP scope

The MVP covers task management with optional deadlines, server validation and persistence, visual deadline emphasis, and a dedicated productivity dashboard. [Scope](docs/product/scope.md) defines the boundaries, component responsibilities, and completion criterion; [Requirements](docs/product/requirements.md) defines the behavioral rules and acceptance scenarios.

## Outside the MVP

Accounts, installation management, recovery, backup, synchronization, offline and multiple-machine operation, persistent local drafts, reminders/notifications, automatic priority, and priority-grouped metrics are outside the MVP. The [Backlog](docs/product/backlog.md) also contains broader desktop improvements, other clients, and integrations. Backlog items must not be used as requirements for MVP specifications or implementation.

## Current project status

The product definition is ready for feature specification work. The [MVP map](docs/product/mvp-map.md) prioritizes the server and identifies dependencies and opportunities for parallel work.

Application code, executable tests, and build/deployment configuration have not been implemented. No feature specification has been created. There is no runnable application or application setup procedure yet.

The [platform and access requirements](docs/product/requirements.md#platform-and-access) define the Windows target, server-side Python baseline, dedicated hosting, and private access. Other technical choices remain open in [AGENTS.md](AGENTS.md#open-questions).

Development uses TLC Spec Driven: **Specify → Design → Tasks → Execute**. [Product requirements](docs/product/requirements.md) remain the approved product inputs; approved feature specifications in `.specs/features/` are the source of truth for implementation. [AGENTS.md](AGENTS.md#source-of-truth-and-workflow) defines sizing, artifact creation, approvals, and verification. Small changes use an inline specification, Medium features use a brief specification, and Large/Complex features use formal design and tasks. Skipped phases do not waive authorization or tests.

[Project state](.specs/STATE.md) records decisions and the current handoff, with links to the approved documentation. The lesson store is initialized with no lessons. The next feature specification is separate work; TLC installation does not authorize implementation or commits.

## TLC skill setup

This project uses **`tlc-spec-driven` 3.3.0**, authored by Felipe Rodrigues and distributed by [Tech Leads Club](https://github.com/tech-leads-club/agent-skills) under CC-BY-4.0. The installed source is pinned to [commit `0ab82f644cd9caf94c65347a50ad934800b0cbc4`](https://github.com/tech-leads-club/agent-skills/tree/0ab82f644cd9caf94c65347a50ad934800b0cbc4/packages/skills-catalog/skills/%28development%29/tlc-spec-driven).

The skill's files live in [.ai/skills/tlc-spec-driven/](.ai/skills/tlc-spec-driven/SKILL.md). The bundle contains `SKILL.md`, phase references in `references/`, and five Python scripts in `scripts/`: `lessons.py`, `validate_spec.py`, `validate_tasks.py`, `validate_state.py`, and `check_commit.py`. Keep the upstream bundle unchanged; repository authorization rules remain in [AGENTS.md](AGENTS.md).

If the bundle is absent, install the pinned source with Codex's bundled `skill-installer` from the repository root. The following PowerShell command uses the default Codex home; resolve the installer under the active Codex home if it differs. The installer refuses to overwrite an existing skill directory.

```powershell
python "$env:USERPROFILE/.codex/skills/.system/skill-installer/scripts/install-skill-from-github.py" `
  --repo tech-leads-club/agent-skills `
  --ref 0ab82f644cd9caf94c65347a50ad934800b0cbc4 `
  --path 'packages/skills-catalog/skills/(development)/tlc-spec-driven' `
  --dest .ai/skills
```

Codex discovers the included skill through a Windows directory junction at `~/.agents/skills/tlc-spec-driven/` pointing to this checkout's `.ai/skills/tlc-spec-driven/`. The junction provides a discovery entry without another copy of the files; see [Codex's skill discovery documentation](https://learn.chatgpt.com/docs/build-skills#where-codex-loads-local-skills). When that discovery path is absent, register the included bundle from the repository root:

```powershell
$tlcSkillDir = (Resolve-Path -LiteralPath .ai/skills/tlc-spec-driven).Path
New-Item -ItemType Directory -Path "$env:USERPROFILE/.agents/skills" -Force | Out-Null
New-Item -ItemType Junction -Path "$env:USERPROFILE/.agents/skills/tlc-spec-driven" -Target $tlcSkillDir
```

This discovery link is machine-local and must be recreated if the checkout moves.

Activate the skill by name and resolve script paths from its installed `SKILL.md`. Scripts use the Python standard library and operate on this repository when run from its root. For the installation above, inspect current state with:

```powershell
$tlcSkillDir = (Resolve-Path -LiteralPath .ai/skills/tlc-spec-driven).Path
python "$tlcSkillDir/scripts/lessons.py" --root . status
python "$tlcSkillDir/scripts/lessons.py" --root . list --status confirmed
python "$tlcSkillDir/scripts/validate_state.py" --root .
```

With no features, the completion validator reports nothing to check. It checks feature validation reports, not `STATE.md`. Specification, task, and implementation gates become applicable when their real artifacts exist. [AGENTS.md](AGENTS.md#tests-and-verification) defines those gates and the repository's test protections. Update lessons only through `lessons.py`; its generated files keep the native format.

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
| [Project state](.specs/STATE.md) | Project decision log and current handoff; references to approved inputs. |
| [Lessons](.specs/LESSONS.md) | Script-generated guidance grounded in feature verification outcomes. |

## Folder structure

The workspace uses the following structure. Empty scaffold directories may not appear in a Git checkout until files are added.

```text
task-analyzer/
|-- .ai/skills/                  # Repository skill bundles
|   |-- grill-me/
|   |-- grilling/
|   `-- tlc-spec-driven/         # SKILL.md, references/, and scripts/
|-- .specs/
|   |-- STATE.md                # Project decisions and handoff
|   |-- LESSONS.md              # Rendered by the installed lessons.py
|   |-- lessons.json            # Machine-owned lessons state
|   `-- features/
|       `-- .gitkeep             # Keeps the directory; no features started
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

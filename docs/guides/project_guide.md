# Project Guide — LLM-Assisted Project Creation

This guide provides step-by-step instructions for an LLM to help a developer create a new software project from scratch. The LLM generates each document one at a time, presenting it to the developer for approval before proceeding to the next.

---

## Prerequisites

Before starting, the developer must provide:

1. **A project idea** — a short description of what the project should do (a few sentences to a few paragraphs).
2. **Language / runtime** — e.g. Python 3.14, Node 22, Go 1.23, etc.
3. **License preference** — e.g. Apache-2.0, MIT, MPL-2.0, GPL-3.0. If a `LICENSE` file already exists in the project root, that license prevails.

The developer may optionally provide:

- Preferred frameworks, libraries, or tools
- Constraints (no UI, no database, must run offline, etc.)
- Target audience (CLI tool, library, web app, etc.)

Additionally, the LLM should ask the developer the following question before writing the stories document:

> **Will this project need CI/CD automation?** For example: GitHub Actions for linting/testing on every push, dynamic code coverage badges (Codecov/Coveralls), and/or automated publishing to a package registry (PyPI, npm, etc.) on tagged releases?

If the answer is yes, the stories document should include a dedicated phase (typically the last phase) covering:

- **CI workflow** — GitHub Actions (or equivalent) running lint, type-check, and tests on push/PR, with a Python/Node/etc. version matrix.
- **Coverage reporting** — uploading coverage to a service like Codecov and adding a dynamic badge to the README.
- **Release automation** — publishing to the package registry on version tags, preferably using trusted publishing (OIDC) to avoid storing API tokens.

If the answer is no, skip this phase entirely.

---

## Workflow Overview

The LLM creates or improves the following documents **in order**, waiting for developer approval after each one:

| Step | Document | Purpose |
|------|----------|---------|
| 1 | `docs/specs/features.md` | What the project does (requirements, not implementation) |
| 2 | `docs/specs/tech_spec.md` | How the project is built (architecture, modules, dependencies) |
| 3 | `docs/specs/stories.md` | Step-by-step implementation plan (phases, stories, checklists) |

After all three documents are approved, the LLM proceeds to scaffold the project and implement stories one by one.

---

## Step 0: Project Setup

Before writing any spec documents, handle project scaffolding:

### License

1. If a `LICENSE` file exists in the project root, read it and identify the license.
2. If no `LICENSE` file exists, create one based on the developer's preference.
3. Record the license identifier (SPDX format, e.g. `Apache-2.0`) — this will be used in `pyproject.toml` (or equivalent) and in file headers.

### Copyright and License Header

Every source file in the project must carry a standard copyright and license header. The header format depends on the license and the file's comment syntax.

**Example for Apache-2.0 in a Python file:**

```python
# Copyright (c) <year> <copyright holder>
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
```

**Example for MIT in a Python file:**

```python
# Copyright (c) <year> <copyright holder>
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction. See the LICENSE file for details.
```

Adapt the comment syntax for the file type (`#` for Python/Shell, `//` for JS/TS/Go, `<!-- -->` for HTML/XML, etc.).

### Project Metadata

When creating the project's package manifest (e.g. `pyproject.toml`, `package.json`, `Cargo.toml`):

- The `license` field must match the `LICENSE` file (use the SPDX identifier).
- Include the copyright holder in the authors/maintainers field.

### README Badges

When a `README.md` is created or updated, include all applicable badges at the top of the file (below the project title). Choose from the following based on what applies to the project:

| Badge | When to include | Example source |
|-------|----------------|----------------|
| **CI status** | If CI is configured (GitHub Actions, etc.) | GitHub Actions badge URL |
| **Package version** | If published to a registry (PyPI, npm, crates.io) | `shields.io/pypi/v/...` |
| **Language version** | If the package specifies supported versions | `shields.io/pypi/pyversions/...` |
| **License** | Always (if a LICENSE file exists) | `shields.io/pypi/l/...` or `shields.io/github/license/...` |
| **Typed** | If the project ships type stubs or a `py.typed` marker | Static `shields.io` badge |
| **Coverage** | If a coverage service is configured (Codecov, Coveralls) | Codecov/Coveralls badge URL |

Use dynamic badges from the package registry (e.g. `shields.io/pypi/...`) when the package is published. Before publication, use static `shields.io` badges or omit registry-dependent badges. Always include the **License** badge. Add badges proactively — do not wait for the developer to ask.

---

## Step 1: Features Document (`docs/specs/features.md`)

### Purpose

Define **what** the project does — requirements, inputs, outputs, behavior — without specifying **how** it is implemented. This is the source of truth for scope.

### Instructions for the LLM

Generate `docs/specs/features.md` with the following sections:

1. **Header** — `# features.md — <Project Name> (<Language>)`
2. **Overview** — one paragraph explaining the document's purpose and cross-references to `tech_spec.md` and `stories.md`
3. **Project Goal** — what the project does, broken into:
   - **Core Requirements** — the essential functionality
   - **Operational Requirements** — error handling, logging, configuration, etc.
   - **Quality Requirements** — deduplication, caching, rate limiting, etc.
   - **Usability Requirements** — who uses it and how (CLI, library, web, etc.)
   - **Non-goals** — what the project explicitly does not do
4. **Inputs** — required and optional inputs with examples
5. **Outputs** — file structures, data formats, schemas
6. **Functional Requirements** — numbered list of features with detailed behavior descriptions and edge cases
7. **Configuration** — config precedence, environment variables, config file format
8. **Testing Requirements** — minimum test coverage expectations
9. **Security and Compliance Notes** — if applicable
10. **Performance Notes** — concurrency, rate limiting, atomicity
11. **Acceptance Criteria** — definition of done for the whole project

### Approval Gate

Present the complete `features.md` to the developer. Do not proceed until the developer approves or requests changes. Iterate as needed.

---

## Step 2: Technical Specification (`docs/specs/tech_spec.md`)

### Purpose

Define **how** the project is built — architecture, module layout, dependencies, data models, API signatures, and cross-cutting concerns.

### Instructions for the LLM

Generate `docs/specs/tech_spec.md` with the following sections:

1. **Header** — `# tech_spec.md — <Project Name> (<Language>)`
2. **Overview** — one paragraph with cross-references to `features.md` and `stories.md`
3. **Runtime & Tooling** — language version, package manager, linter, test runner, etc.
4. **Dependencies** — tables for runtime, optional, system, and development dependencies with purpose for each
5. **Package Structure** — full directory tree with one-line descriptions per file
6. **Key Component Design** — for each major module:
   - Function/method signatures (with types)
   - Brief description of behavior
   - Edge cases handled
7. **Data Models** — full model definitions with field types and defaults
8. **Configuration** — settings model with all fields, types, defaults, and precedence rules
9. **CLI Design** — subcommands table, shared flags, exit codes (if applicable)
10. **Library API** — public API with usage examples (if applicable)
11. **Cross-Cutting Concerns** — retry strategy, rate limiting, logging, caching, atomic writes, etc.
12. **Testing Strategy** — unit tests, integration tests, and what each covers

The sections above are a starting point. Adapt them to fit the project type — for example, a web app may need sections on routing, database schema, and deployment; a mobile app may need sections on screen navigation, platform APIs, and build targets; a bash utility may only need a few of the above. Add, remove, or rename sections as appropriate.

### Approval Gate

Present the complete `tech_spec.md` to the developer. Do not proceed until approved.

---

## Step 3: Stories Document (`docs/specs/stories.md`)

### Purpose

Break the project into an ordered sequence of small, independently completable stories grouped into phases. Each story has a checklist of concrete tasks.

### Instructions for the LLM

Generate `docs/specs/stories.md` following this exact format:

#### Document Header

```markdown
# stories.md — <Project Name> (<Language>)

<One paragraph describing the document. Mention that stories are organized by phase
and reference modules defined in `tech_spec.md`.>

<One paragraph explaining the numbering scheme (e.g. A.a, A.b) and version bumping
convention. Mention that stories with no code changes have no version number.
Mention the [Planned]/[Done] suffix convention.>

---
```

#### Phase Sections

Each phase is a `## Phase <Letter>: <Name>` heading followed by stories.

Recommended phase progression:

| Phase | Name | Purpose |
|-------|------|---------|
| A | Foundation | Hello world, project structure, core models, config, logging |
| B | Core Services | The main functional modules (one story per service) |
| C | Pipeline & Orchestration | Wiring services together, caching, concurrency, error handling |
| D | CLI & Library API | User-facing interfaces |
| E | Testing & Quality | Test suites, coverage, edge case tests |
| F | Documentation & Release | README, changelog, final testing, polish |
| G | CI/CD & Automation | GitHub Actions, coverage badges, release automation (if requested) |

Phases may be added, removed, or renamed to fit the project. Phase G (CI/CD) is only included if the developer answered "yes" to the CI/CD question in the prerequisites.

#### Story Format

Each story follows this format:

```markdown
### Story <Phase>.<letter>: v<version> <Title> [Planned]

<Optional one-line description.>

- [ ] <Task 1>
  - [ ] <Subtask 1a>
  - [ ] <Subtask 1b>
- [ ] <Task 2>
- [ ] <Task 3>
```

Rules:

- **Story ID**: `<Phase letter>.<lowercase letter>` — e.g. `A.a`, `A.b`, `B.a`
- **Version**: semver, bumped per story. Stories with no code changes omit the version.
- **Status suffix**: `[Planned]` initially, changed to `[Done]` when completed.
- **Checklist**: use `- [ ]` for planned tasks, `- [x]` for completed tasks. Subtasks are indented with two spaces.
- **First story** should always be a minimal "Hello World" — the smallest possible runnable artifact.
- **Homepage**: If a project homepage (e.g. `docs/index.html`) was created during the planning phase, include a task in the Hello World story to verify it is present and references the correct repository URL.
- **Each story** should be completable in a single session and independently verifiable.
- **Verification tasks** (e.g. "Verify: command prints version") should be included where appropriate.

### Approval Gate

Present the complete `stories.md` to the developer. Do not proceed until approved.

---

## Step 4: Implementation

Once all three documents are approved, begin implementing stories in order:

1. **Start with Story A.a** (Hello World).
2. For each story:
   a. Read the story's checklist.
   b. Implement all tasks.
   c. Add the copyright/license header to every new source file.
   d. Run tests if applicable.
   e. Mark checklist items as `[x]` and change the story suffix to `[Done]`.
   f. Bump the version in the package manifest and source (if the story has a version).
   g. Present the completed story to the developer for approval.
3. **Pause after each story.** Do not proceed to the next story until the developer says "proceed" (or equivalent approval). This is a hard gate — never auto-advance.

### File Header Reminder

Every new source file created during implementation must include the copyright and license header as the very first content in the file (before any code, docstrings, or imports).

---

## Summary

| Step | Action | Gate |
|------|--------|------|
| 0 | Set up LICENSE, determine header format | Developer confirms license |
| 1 | Write `docs/specs/features.md` | Developer approves |
| 2 | Write `docs/specs/tech_spec.md` | Developer approves |
| 3 | Write `docs/specs/stories.md` | Developer approves |
| 4 | Implement stories one by one | Developer approves each story |
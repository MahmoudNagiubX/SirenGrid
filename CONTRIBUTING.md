# Contributing to SirenGrid

## Before You Start

1. Read `docs/MASTER_PLAN.md` before implementing product behavior.
2. Confirm your task is inside the approved scope.
3. If a product decision is unclear, ask the team instead of inventing behavior.
4. Search relevant public GitHub repositories and technical references before building a non-trivial subsystem from scratch.
5. Reuse code only after understanding it and confirming that it fits SirenGrid.

## Branching

Use one focused branch per task.

Suggested naming:

- `feature/<short-name>`
- `fix/<short-name>`
- `research/<short-name>`
- `docs/<short-name>`

Avoid direct feature work on `main`.

## Pull Requests

Each PR should state:

- what was implemented,
- which Master Plan requirement it covers,
- files or subsystems affected,
- tests/verification performed,
- what is intentionally not implemented,
- any assumptions,
- reused/reference repositories, if any.

Keep PRs focused. Do not mix unrelated refactors or features.

## Product Scope

The Master Plan is the product source of truth.

Do not silently:

- add a major feature,
- remove an approved feature,
- change AI authority,
- change the human-approval boundary,
- change real vs simulated integration status,
- change the geographic MVP,
- reinterpret product metrics.

If one of these decisions is required, get explicit team approval and record it in `docs/DECISIONS.md` when appropriate.

## Quality Rules

- Do not call a feature complete without verification.
- Do not use hardcoded/demo-only logic while presenting it as real implementation.
- Do not present simulated integrations as official/live systems.
- Prefer small, clear files with one responsibility over unnecessary abstractions.
- Do not add dependencies without a clear reason.
- Do not commit secrets, API keys, private credentials, or local environment files.

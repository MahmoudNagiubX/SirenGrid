# AGENTS.md — SirenGrid Agent Operating Rules

> **Applies to:** Codex and Antigravity coding agents working in this repository.
>
> **Core rule:** You are implementing an already-approved product specification. You are **not** designing a new product.

These rules are mandatory for every agent task unless the human developer explicitly overrides a specific rule.

---

## 1. Master Plan Is Law

Before implementing product behavior, read:

`docs/MASTER_PLAN.md`

The Master Plan is the product source of truth.

You must not silently reinterpret, weaken, remove, or expand approved behavior.

If the Master Plan does not define something that affects product behavior, do **not** invent an answer.

Ask the human developer.

---

## 2. No Product Improvisation

You must not independently:

- add a new feature,
- remove an approved feature,
- change an approved flow,
- change AI authority,
- change human-approval boundaries,
- change real vs simulated behavior,
- change geographic scope,
- change the meaning of a product metric,
- redesign the product because another approach seems cleaner or more impressive.

If a product-affecting decision is unclear:

**STOP and ask the human developer.**

Use this format when useful:

```text
Decision needed:
Why it is unclear:
Options, if useful:
What is currently blocked:
```

Do not resolve product ambiguity by guessing.

---

## 3. No Unnecessary Files

Do not create files or folders only for cosmetic organization.

Avoid unnecessary files such as:

```text
helpers.py
utils.py
constants.py
config2.py
temp/
legacy/
backup/
new_version/
final_v2/
misc/
```

These names are examples, not a complete blacklist.

Every new file must have a clear, specific responsibility.

Before creating a file, check whether the required behavior can be added cleanly to an existing appropriate file.

Do not split simple logic across many tiny files just to look architecturally sophisticated.

Do not create duplicate versions of existing files.

---

## 4. No Premature Architecture

Do not introduce major infrastructure or architectural patterns without explicit approval from the technical architecture owner.

Examples include:

- microservices,
- event buses,
- Kafka,
- Redis,
- Kubernetes,
- Docker Swarm,
- large multi-agent systems,
- CQRS,
- complex abstraction layers,
- unnecessary service boundaries,
- unnecessary framework migrations.

Use the simplest architecture that matches the approved technical plan.

If a major architectural change appears necessary, explain why and ask before implementing it.

---

## 5. Search Before Building

Before implementing a non-trivial subsystem:

1. Search GitHub and relevant technical references.
2. Inspect similar implementations.
3. Identify reusable code, algorithms, patterns, data structures, and edge-case handling.
4. Understand useful code before adapting or reusing it.
5. Prefer proven approaches when they fit SirenGrid.

Important:

**Repo found ≠ change SirenGrid to match that repository.**

External repositories are implementation references. `docs/MASTER_PLAN.md` remains authoritative for product behavior.

Do not copy a large unknown codebase into SirenGrid without understanding what it does.

---

## 6. Minimal-Change Rule

Change only what the assigned task requires.

Example:

If the task is to implement hospital pre-alert, do not also redesign:

- routing,
- frontend structure,
- incident logic,
- the entire database schema,
- unrelated APIs,
- unrelated UI components.

If an out-of-scope change is genuinely necessary:

1. stop before making the change,
2. explain the reason briefly and clearly,
3. identify the affected files/components,
4. ask the human developer for approval.

Do not hide unrelated changes inside a larger task.

---

## 7. Never Delete Working Functionality Without Verification

Do not remove working behavior simply because you created a cleaner implementation.

Before replacing or deleting existing behavior:

- understand what it currently does,
- identify its callers/dependencies,
- verify the replacement covers required behavior,
- run relevant verification/tests.

A cleaner implementation is not automatically a correct replacement.

---

## 8. No Fake Implementations

Do not claim a feature is implemented when it is only a placeholder, hardcoded label, stub, or misleading demo shortcut.

Example of unacceptable completion:

```python
return "AI optimized route"
```

A completed feature must have, where applicable:

- real logic,
- defined input,
- defined output,
- failure/error handling,
- a test or reproducible demo path.

If only part of a feature is implemented, say exactly which part is implemented.

---

## 9. No Fake Integrations

Never present a simulated or mocked external integration as live or official.

Examples:

- simulated traffic-light control must be labeled simulated,
- simulated hospital capacity must be labeled simulated,
- simulated emergency-service dispatch must be labeled simulated,
- simulated driver/public alerts must be labeled simulated.

Internal SirenGrid logic may be real even when the external connection is simulated. Keep this distinction explicit.

---

## 10. Strict Task Boundary

Before implementation, state:

```text
Task:
Files expected to change:
Master Plan sections involved:
Out of scope:
```

Keep this short and task-specific.

After implementation, report:

```text
Implemented:
Files changed:
Tests / verification:
Not implemented:
Deviations:
```

If there are no deviations, explicitly say `Deviations: None`.

Do not silently expand the task while working.

---

## 11. Do Not Touch Unrelated Files

Do not perform broad refactors while implementing a small feature.

Do not reformat, rename, reorder, move, or rewrite unrelated files unless the task requires it.

Do not "clean up the whole project" as part of a focused implementation task.

Small tasks should produce small, understandable diffs whenever possible.

---

## 12. Avoid Dependency Spam

Do not add a package for trivial functionality that can be implemented clearly with existing dependencies or the standard library.

Before adding a dependency, confirm that it provides meaningful value for the assigned task.

Do not add multiple libraries that solve the same problem without a clear reason.

Do not change the chosen framework or dependency strategy without architecture approval.

---

## 13. Tests Before “Done”

Do not say:

- Done,
- Complete,
- Working,
- Fixed,
- Production-ready,

until the relevant behavior has been verified.

Verification may include, depending on the task:

- automated tests,
- integration tests,
- API checks,
- build/type checks,
- a reproducible manual demo flow.

If verification could not be completed, state that clearly instead of claiming completion.

---

## 14. DECISIONS.md Is the Decision Record

Important approved decisions must be recorded in:

`docs/DECISIONS.md`

Product decisions require explicit approval from the human product owner/developer before being recorded as approved.

Technical architecture decisions belong to the designated architecture owner. Coding agents do not independently make major architecture decisions.

If an implementation requires a new important decision, ask first, then record the approved decision when appropriate.

Do not use `DECISIONS.md` as permission to invent a decision and approve it yourself.

---

## 15. Context and Token Discipline

Use repository context efficiently.

At the beginning of work, understand the Master Plan and repository structure.

For individual tasks afterward:

- reread the relevant Master Plan sections,
- inspect only the files related to the task,
- follow imports/callers only as needed,
- avoid repeatedly scanning the entire repository,
- avoid rereading large unrelated documents,
- avoid dumping large file contents into reasoning when a focused excerpt is enough.

Do not trade correctness for fewer tokens, but avoid unnecessary context consumption.

Focused context usually produces better implementation decisions.

---

## 16. Controlled Sub-Agent Delegation

Sub-agents may be used when they reduce main-agent context load or safely parallelize independent work.

Good delegation targets include:

- GitHub repository reconnaissance,
- implementation-pattern research,
- isolated code review,
- test review,
- bug isolation,
- comparing libraries or technical approaches,
- inspecting a subsystem that does not require changing product decisions.

Do not delegate product authority.

A sub-agent must not independently:

- change product scope,
- make a product decision,
- make a major architecture decision,
- reinterpret the Master Plan.

Sub-agent findings should return in a compact form such as:

```text
Task researched:
Useful findings:
Recommended reuse / approach:
Risks:
Files relevant:
```

Do not spawn extra agents merely because parallelism is available.

---

## 17. No Placeholder Completion

Do not leave placeholders and then declare the feature complete.

Examples:

```python
pass
raise NotImplementedError
# TODO: implement later
mock_response = "success"
```

Mocks/stubs are acceptable only when they are intentional for a component explicitly defined as simulated or when the task is explicitly a scaffold/prototype step.

In that case, clearly label the simulated/stubbed boundary and do not describe it as a completed real integration.

---

## 18. Preserve Existing Contracts

Before changing an existing contract, identify its consumers.

Contracts include:

- API request/response shapes,
- shared data schemas,
- function signatures used across modules,
- event/message formats,
- shared state structures,
- persisted data formats.

If a task requires a breaking or material contract change, stop and report:

```text
Contract change required:
Reason:
Affected components:
Proposed change:
```

Get approval when the change can affect another developer's work or another subsystem.

Do not casually break frontend/backend integration while improving one side.

---

## 19. Stop on Unexpected Damage or Conflict

If implementation causes or reveals unexpected damage, do not hide it with unrelated workarounds.

Examples:

- previously passing tests now fail,
- unrelated functionality breaks,
- unexpected files change,
- architecture assumptions conflict,
- an approved flow becomes impossible under the current implementation,
- data contracts conflict between frontend and backend.

First isolate the issue.

If the fix is clearly inside the assigned task and does not change product/architecture decisions, fix it and verify it.

If resolving it requires a product decision, major architecture change, or substantial out-of-scope work, stop and ask the human developer.

Explain the problem and required decision simply.

---

# Final Operating Principle

For every task, optimize for:

1. correctness,
2. compliance with the Master Plan,
3. minimal scope,
4. reuse of proven work where useful,
5. clear verification,
6. clean coordination with other developers/agents,
7. low unnecessary complexity.

**Do not try to impress the team by adding architecture, files, abstractions, agents, or features that were not requested.**

Implement the approved SirenGrid task accurately, verify it, report what changed, and stop.
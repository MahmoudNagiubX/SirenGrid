# SirenGrid Phase 03 TDD Implementation Plan

## Execution rules

- Delegate exactly one bounded task at a time to Antigravity.
- Antigravity must not commit, branch, push, redesign architecture, or widen
  scope. Codex inspects every diff and runs focused tests before the next task.
- Each behavioral task follows RED -> GREEN -> focused regression.
- Preserve the complete Phase 01/02 suite after every checkpoint.

## Task 1: Contracts, report/evidence, and lifecycle foundation

**Dependencies:** approved design only.

**Scope:** Add the minimum report/evidence persistence and manual contracts;
add deterministic lifecycle transition validation and transactional transition
handling; preserve the existing manual intake and plan-generation behavior.

**Acceptance tests:**

- report/evidence manual records preserve source, timestamps, reality, and
  provenance without AI processing;
- legal forward transitions succeed once and append one timeline event;
- illegal, backward, exceptional-arbitrary, and stale transitions return
  visible conflicts without mutation;
- current Golden Flow still starts at `ACTIVE_UNCONFIRMED`, generates plans
  at `AWAITING_APPROVAL`, and approves successfully.

**Likely files:** `backend/app/models.py`, `backend/app/schemas.py`,
`backend/app/incidents.py`, a focused domain/service module, and focused tests.

## Task 2: Timeline endpoint and manual correction

**Dependencies:** Task 1.

**Scope:** Add `GET /api/v1/incidents/{id}/timeline` and the typed atomic facts
patch using the existing `TimelineEvent.details_json` for history.

**Acceptance tests:**

- stale version returns 409 with zero mutation;
- valid multi-field correction increments incident version once, returns the
  changed fields and dirty flag, and appends one per-field audit event;
- semantic no-op returns unchanged state with no version/event mutation;
- later code paths do not silently remove operator-corrected provenance.

## Task 3: Transactional resource operational locking

**Dependencies:** Task 1.

**Scope:** Add minimum version-checked resource status/assignment operations
needed by Phase 03 simulation, using the proven single-process SQLite locking
strategy.

**Acceptance tests:**

- stale resource mutation returns 409;
- an assigned resource cannot be assigned to another active incident;
- concurrent assignment attempts yield one winner and no duplicate state;
- no unavailable resource is used as a fallback.

## Task 4: WebSocket operations manager and envelope

**Dependencies:** Tasks 1-3.

**Scope:** Add the process-local connection manager, canonical event publisher,
and `/api/v1/ws/operations`; publish only events emitted by implemented
behavior.

**Acceptance tests:**

- connected clients receive the locked envelope;
- stream versions are globally monotonic during one process lifetime;
- incident-associated and resource-only `incident_id` behavior is correct;
- REST remains sufficient for recovery and no placeholder events appear.

## Task 5: Deterministic route-progress movement

**Dependencies:** Tasks 3-4.

**Scope:** Add explicit route-progress movement over the approved route geometry
and simulated resource state updates.

**Acceptance tests:**

- cumulative-distance interpolation follows the stored route geometry;
- progress is bounded, monotonic, idempotent for repeats, and rejects reverse
  movement;
- unassigned/wrong-incident movement fails without mutation;
- provenance remains `SIMULATED`; no speed, cadence, ETA, or alternate route
  is fabricated;
- movement emits appropriate timeline/live events.

## Task 6: REST/live-state integration and regression review

**Dependencies:** Tasks 1-5.

**Scope:** Expose only necessary incident/resource live-state fields and run
  the integrated manual movement/REST/WebSocket path.

**Acceptance tests:**

- REST reads remain canonical and include ID, status, coordinates, reality,
  source, freshness, and version;
- Phase 01 Golden Flow and all Phase 02 routing/traffic tests remain green;
- one-worker REST and WebSocket smoke passes;
- full pytest, Ruff, compileall, and scope/reality/secrets audits pass.

## Checkpoints

- After Task 1: full existing suite plus lifecycle/report tests.
- After Task 3: full existing suite plus locking/concurrency tests.
- After Task 5: full existing suite plus movement/WebSocket tests.
- After Task 6: final Phase 03 review; do not begin Phase 04.

# SirenGrid Phase 03 Operational Core Design

**Status:** Owner-approved design gate, 2026-09-07

## Goal

Extend the Phase 01 incident/resource foundation into the Phase 03 incident,
resource, simulation, timeline, and realtime operational core without starting
Phase 04 or changing the Phase 01/02 contracts unnecessarily.

## Locked boundaries

- Repository branch remains `feature/phase-01-golden-flow`.
- One FastAPI process/worker and SQLite remain the operational runtime.
- Manual/operator-created input is the only Phase 03 input path. No AI, ASR,
  image interpretation, report fusion, or duplicate fusion is added.
- Resource coordinates/status are `SIMULATED` operational data with explicit
  provenance/freshness metadata.
- REST is canonical state and WebSocket is transport/invalidation only.
- No Redis, event bus, distributed lock, frontend, coverage, hospital,
  corridor, replanning, or Phase 04+ behavior.

## Incident/report/evidence contracts

Build on the existing `Incident` model. Add only the report/evidence metadata
required by the architecture:

- report: incident association (nullable until attached), source type,
  source reference, raw text/transcript, location metadata, received time,
  reality label, and processing status;
- evidence: report association, type, URI/reference, extracted facts,
  provenance, confidence/support, and creation time.

Phase 03 persists manual/operator records only. Historical evidence is
append-only and never silently overwritten.

## Lifecycle

Use the locked values:

`RECEIVED`, `INTERPRETING`, `ACTIVE_UNCONFIRMED`, `RESPONSE_PROPOSED`,
`AWAITING_APPROVAL`, `RESPONSE_ACTIVE`, `EN_ROUTE`, `ON_SCENE`,
`TRANSPORT_ACTIVE`, `HANDOVER`, `CLOSED`, `REQUIRES_REVIEW`,
`DUPLICATE_MERGED`, and `CANCELLED_FALSE_REPORT`.

Normal transitions are strict and forward-only. `TRANSPORT_ACTIVE` is the
conditional branch after `ON_SCENE`; non-transport incidents use
`ON_SCENE -> HANDOVER -> CLOSED`. Exceptional states are controlled backend
transitions, not arbitrary client strings. Existing manual intake continues
to create `ACTIVE_UNCONFIRMED`; plan generation continues to expose
`AWAITING_APPROVAL` and may record the conceptual response-proposed step in
one atomic operation. Approval remains `AWAITING_APPROVAL -> RESPONSE_ACTIVE`.

Every successful transition is version-checked, increments the incident
version once, and appends a timeline event in the same transaction.

## Manual correction

`PATCH /api/v1/incidents/{id}/facts` accepts one atomic typed multi-field
patch containing:

- `expected_incident_version`;
- `operator_reference`;
- typed optional incident fact fields.

The complete patch is validated before mutation. A stale expected version
returns HTTP 409. A semantic no-op returns the unchanged incident, an empty
`changed_fields`, and `downstream_inputs_dirty: false` without incrementing
the version or creating an event.

A successful correction increments the incident version once, marks current
corrected-field provenance as operator-corrected in the existing provenance
structure, and appends one `FACTS_CORRECTED` timeline event. The event stores
per-field old/new values, operator reference, and timestamp. Any actual
planning-relevant change returns `downstream_inputs_dirty: true`; Phase 03
does not recalculate or replan.

## Resource locking and simulated state

Resource mutations are version-checked and transactional. A resource already
assigned to an incompatible active incident cannot be assigned again; stale
or unavailable mutations return visible conflicts. Resource state updates
preserve the Phase 01 single-process SQLite strategy and carry explicit
`SIMULATED` provenance and freshness metadata.

## Deterministic movement

Movement is an explicit command over the already approved/active route:

`route_progress` is a number in `[0.0, 1.0]`, where `0.0` is route start and
`1.0` is route end. Position is interpolated by cumulative route distance
over the stored route geometry, never by vertex count. The resource must be
assigned to the route's incident. Identical progress is idempotent; backward
progress is rejected. No wall-clock ticker, speed, cadence, or ETA claim is
introduced, and movement does not implicitly change lifecycle status.

## WebSocket operations stream

Expose `/api/v1/ws/operations` using a process-local connection manager.
Published events use one process-local global monotonic sequence for the
envelope version:

```json
{
  "event": "incident.updated",
  "incident_id": "... or null",
  "timestamp": "...",
  "version": 1,
  "payload": {}
}
```

Domain/entity versions remain in payload where applicable. Resource-only
events may have a null `incident_id`; incident-associated resource events
carry the incident ID. Reconnect always requires REST recovery. A client
detecting a sequence gap must refetch canonical REST state. No persistent or
distributed stream sequence is added, and no Phase 04+ placeholder events are
published.

## Reconnaissance

Performed against the current Phase 01/02 backend, tests, GraphML route
artifacts, provenance metadata, and approved architecture/decision files.
The Phase 01 approval/version and SQLite `BEGIN IMMEDIATE` pattern is reused.
Approved donor reconnaissance is recorded in the Phase 01/02 review files:
the pinned Egypt-Smart-City-Digital-Twin reference and selective ResQPath
reference were inspected. Their weather behavior, OpenRouteService,
unavailable-resource fallback, straight-line fallback, and route-failure-to-
zero behavior remain rejected.

## Out of scope

AI/ASR/images, report fusion, coverage, hospitals, corridor/driver alerts,
full freshness/replanning, multi-incident optimization beyond assignment
locking, scenario engine, frontend, and Phase 04+ behavior.

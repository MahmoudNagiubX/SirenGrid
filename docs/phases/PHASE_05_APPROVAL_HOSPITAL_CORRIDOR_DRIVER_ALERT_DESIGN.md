# Phase 05 Design — Approval + Hospital + Corridor + Driver Alert

## Scope

Phase 05 extends the approved Phase 01–04 response-plan flow with hospital
selection, simulated hospital pre-alert, approved-route corridor extraction,
simulated signal priority, and simulated forward driver alerts. Hospital,
corridor, and alert states remain parallel operational substates; they do not
add arbitrary incident lifecycle values.

## Truth boundaries

- OSM/Overpass hospital and signal assets are real public/derived static data.
- Hospital operational state, pre-alert acknowledgement, signal priority, and
  alert delivery are `SIMULATED`.
- Static capacity is not current free capacity; unavailable fields remain
  unknown/null.
- Routing uses the existing OSM/TomTom captured routing contract. Corridor
  priority never changes route ETA.
- REST is canonical and the existing process-local WebSocket publishes only
  domain updates/invalidation.

## Hospital flow

Explicit structured facts provide `transport_required` and known hospital
capability tags. Unknown transport requires operator confirmation. For true
transport, the system loads the static OSM registry, overlays explicit
simulated state, filters only explicit not-accepting/confirmed-incompatible/
unreachable candidates, routes from the approved active responder route
origin, and ranks candidates using `SIRENGRID_PROTOTYPE_HOSPITAL_SCORE_V1`.

The lower-is-better score uses the approved ETA, capability, load, freshness,
and neutral static-capacity terms. Options retain raw/normalized/weighted
terms, uncertainty, provenance, and one coherent routing/traffic snapshot.

Destination selection is version-safe, transactional, and separate from plan
approval. Pre-alert is possible only after destination selection and uses
known facts only. `SimulatedHospitalGateway` implements an idempotent
REQUESTED → SENT → ACKNOWLEDGED or FAILED flow without automatic retry.

## Corridor flow

The corridor uses only the approved active responder route. OSM signal points
within 50 m are projected to the route and ordered by route distance. Signal
priority uses the approved 30-second prototype lead time and explicit
simulated states. It does not alter routing or ETA.

## Driver-alert flow

Explicit simulated route progress drives a 500 m forward route segment buffered
by 30 m. Each explicit refresh/movement command replaces the prior region and
sets a 120-second simulated expiry. Route end expires the region. No ticker,
private patient data, or real delivery integration is introduced.

## API shape

Use focused REST endpoints for hospital options/details/destination/pre-alert,
corridor state/priority, driver-alert state/refresh, and one aggregate
incident operational-state read. Reuse existing incident, plan, timeline,
resource, routing, and WebSocket conventions.

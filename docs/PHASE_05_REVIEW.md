# PHASE 05 REVIEW

Implemented:

- Hospital registry and operational-state API backed by the approved 27-feature OSM/Overpass asset.
- Version-safe hospital destination selection and replacement before pre-alert.
- `SimulatedHospitalGateway` with idempotent success and deterministic failure injection.
- Approved-route corridor extraction using the static OSM traffic-signal asset.
- `TrafficSignalGateway` simulated priority state machine.
- Explicit route-progress driver-alert regions and `DriverAlertGateway` simulation boundary.
- Read-only aggregate incident operational-state view.
- Timeline and process-local WebSocket invalidation events for Phase 05 operations.

Files changed:

- `backend/app/config.py`, `incidents.py`, `models.py`, `schemas.py`, `main.py`, `resources.py`
- `backend/app/hospitals.py`, `hospital_gateway.py`, `hospital_api.py`
- `backend/app/corridor.py`, `corridor_api.py`, `traffic_signal_gateway.py`
- `backend/app/driver_alert.py`, `driver_alert_api.py`, `operational_api.py`
- Phase 05 hospital, corridor, driver-alert, and integrated-smoke tests
- `docs/DECISIONS.md`, Phase 05 design/TDD documents, and this review

Hospital registry:

- Static registry loads 27 hospital features from `nasr_city_emergency_facilities.geojson`.
- Source identity is stable and exact duplicate handling is deterministic; no fuzzy name merge is used.

Hospital filtering:

- Filters only explicit `NOT_ACCEPTING`, confirmed incompatible capabilities, and unreachable routes.
- Unknown capability remains unknown and is scored with the approved uncertainty penalty.

Hospital ranking:

- Uses `SIRENGRID_PROTOTYPE_HOSPITAL_SCORE_V1`, lower-is-better, ETA normalizer 900 seconds, and locked weights.
- Static capacity is null/unknown for this asset and has neutral weight.
- Raw terms, normalized terms, weights, weighted terms, uncertainty, and final score are persisted.

Hospital destination approval:

- Requires the current approved response plan, explicit `transport_required=true`, current option-set membership, and matching versions.
- Replacement increments incident version once before any pre-alert; replacement after pre-alert request is rejected.
- No responder state is mutated.

Hospital pre-alert:

- Known-facts-only payloads.
- Simulated `REQUESTED -> SENT -> ACKNOWLEDGED` or `REQUESTED -> FAILED` transitions are audited.
- Requests are idempotent and failed alerts are not automatically retried.

Hospital gateway:

- `SimulatedHospitalGateway` is the only delivery boundary; no real hospital integration is claimed.

Corridor extraction:

- Uses only the explicitly selected resource route from the current approved plan.
- Existing OSM signal features are matched within the locked 50 m tolerance, projected, deduplicated, and ordered along route distance.
- Multi-route plans require an explicit resource route identifier; no route is silently selected.

Signal priority simulation:

- `TrafficSignalGateway` exposes only the approved simulated states and 30-second prototype lead time.
- Priority state does not mutate OSM, TomTom, approved route geometry, or any ETA.

TrafficSignalGateway:

- Process-local simulated transition boundary; no Cairo signal-control integration exists.

Driver alert region:

- Explicit route progress drives the next 500 m of the approved route buffered by 30 m.
- Previous regions are expired on explicit movement/refresh, route end produces an expired state, and expiry is 120 seconds.
- Geometry is derived from the approved route and labeled `REAL_DERIVED`; delivery is `SIMULATED`.

DriverAlertGateway:

- Explicit simulation boundary; no SMS, telecom, or direct driver-network delivery exists.

Timeline/WebSocket integration:

- Material destination, pre-alert, corridor, and driver-alert changes append timeline history.
- Existing process-local operations events are used for REST-canonical invalidation/update.

API contracts:

- `/api/v1/hospitals`
- `/api/v1/incidents/{id}/hospital-options`
- `/api/v1/incidents/{id}/hospital-destination`
- `/api/v1/incidents/{id}/hospital-destination/select`
- `/api/v1/incidents/{id}/hospital-prealert`
- `/api/v1/incidents/{id}/corridor`
- `/api/v1/incidents/{id}/corridor/priority`
- `/api/v1/incidents/{id}/resources/{resource_id}/driver-alert`
- `/api/v1/incidents/{id}/resources/{resource_id}/driver-alert/refresh`
- `/api/v1/incidents/{id}/operational-state`

Tests:

- Full pytest: `327 passed` using `python -m pytest backend/tests -q --disable-warnings`.
- Focused Phase 05: 18 passed across hospital registry/API, corridor, gateway, driver-alert, and integrated-smoke tests.
- Golden Flow: included in the clean 327-test regression and passed.
- Integrated smoke: passed against real OSM graph, hospital asset, and signal asset with provider fallback behavior preserved.
- Approval/resource/WebSocket regressions: included in the clean full suite and passed.
- Ruff: PASS (`ruff check backend`).
- Compileall: PASS (`python -m compileall -q backend`).
- Diff check: PASS (`git diff --check`).

Reality/provenance audit:

- OSM hospital/signal facts remain `REAL_PUBLIC` or `REAL_DERIVED`.
- Simulated hospital state, gateway acknowledgement, signal priority, responder positions, and driver-alert delivery remain `SIMULATED`.
- Hospital routing preserves OSM base/TomTom fallback provenance and does not label provider failures as live traffic.
- Derived corridor and alert geometry retains source route references.

Version/concurrency audit:

- SQLite `BEGIN IMMEDIATE` protects destination selection, pre-alert request, corridor priority, and simulation-state updates.
- Destination replacement and stale incident/plan/option versions are rejected visibly.
- Pre-alert uniqueness and idempotent lookup prevent duplicate alerts.
- Existing Phase 01–04 approval/resource safeguards remain green.

Hospital uncertainty audit:

- Missing capacity, accepting state, and capabilities remain unknown/null unless an explicit simulated state is supplied.
- No MOHP, live hospital, or inferred medical facts were added.

Corridor truthfulness audit:

- Only approved response routes and real OSM signal points are used.
- No named-road shortcut, straight-line corridor, alternate route, or real signal preemption is claimed.

Driver-alert privacy audit:

- Alert payloads contain route/resource/geographic state only; no patient or diagnosis facts are included.

Secrets audit:

- No secrets were added, printed, or committed. Existing `TOMTOM_API_KEY` environment configuration remains environment-only.

Phase 06 leakage audit:

- No AI extraction, ASR, image interpretation, report fusion, or other Phase 06 behavior was implemented.

Repo reconnaissance:

- Reviewed the current Phase 01–04 models, routing/traffic contracts, route-progress movement, map assets, provenance manifest, timeline/WebSocket conventions, and tests.
- Reused existing SQLAlchemy transaction patterns, routing graph, traffic snapshot contract, resource movement state, provenance labels, and OSM assets.

References/reuse:

- No unsafe donor behavior or additional repository code was copied.

Not implemented:

- Real hospital integration, real signal control, real driver delivery, background scheduling, ETA reduction from corridor priority, frontend, and Phase 06+ systems remain out of scope.

Owner decisions:

- PD-018 through PD-027 are recorded in `docs/DECISIONS.md` and reflected in the Phase 05 design/TDD documents.

Deviations:

- None. The explicit `resource_id` corridor input for multi-route plans is documented as the minimum route-selection contract and prevents silent route choice.

Blocking issues:

- None. Repeated ad-hoc pytest invocations encountered Windows temporary-directory permission errors in the local test harness, but the clean full backend run and focused suites provide passing evidence.

Verdict: PASS

# PHASE 02 REVIEW

Implemented:

- Phase 02 geospatial and traffic runtime only, on the owner-designated long-lived `feature/phase-01-golden-flow` branch.
- Locked prototype configuration and frozen traffic snapshot models; strict TomTom Flow Segment parsing; one total monotonic refresh deadline; process-local refresh caching; conservative corridor-first matching; immutable graph-bound overlays; independent base and traffic-aware route calculations; minimum API extensions; and a rollback-safe OSMnx/Overpass refresh command.
- Phase 02 implementation commits: `c15a1b6`, `9e2e81f`, `d863b78`, `d4d7fc5`, `917c9f3`, `dc19311`, and `8c863f7`. The approved design/TDD commits are `102e88c`, `3591160`, `61f85a5`, `7997891`, and `d39ae6b`.

Files changed:

- Runtime/config/API: `backend/app/config.py`, `backend/app/main.py`, `backend/app/map.py`, `backend/app/routing.py`, `backend/app/schemas.py`, and `backend/app/traffic/`.
- Refresh tooling: `backend/scripts/refresh_nasr_city_geospatial.py` and package marker.
- Tests: Phase 02 TomTom, freshness, matching, runtime, routing, API, refresh, asset, map, contract, and Golden Flow coverage under `backend/tests/`.
- Data: refreshed Nasr City GraphML and emergency facilities; new traffic-signal and graph-derived corridor-sample GeoJSON; updated per-artifact provenance. The pinned donor boundary and 500 m grid were retained.
- Documentation: approved Phase 02 design, TDD plan, and this review.

Geospatial refresh:

- **PASS.** One owner-approved bounded OSMnx/Overpass acquisition was run against the retained Nasr City polygon. It produced a validated 7,348-node/17,439-edge road graph, 41 physical emergency-facility features, 14 physical traffic-signal features, and 5 named corridor sample points.
- Refresh output is built in staging. Directed/MultiDiGraph shape, non-empty topology, positive base metrics, source one-way state, GeoJSON structure, UTF-8 road names, sample-to-named-edge binding, record counts, and SHA-256 manifest hashes are checked before publication.
- Publication uses a checked sibling-directory swap and restores the byte-identical prior target when the publish swap fails. A valid-but-hash-mismatched staged artifact is rejected. Failed acquisition/validation never invokes publication.
- Provenance records `DIRECT_OSMNX_OVERPASS_OWNER_APPROVED`; Geofabrik Egypt remains the approved fallback/reproducibility source and was not claimed as used. Retained boundary/grid provenance still identifies donor commit `93ca9e90e2fc52c914dd5ccbe42bdc84ce745d3d`.

Base graph:

- **PASS.** The refreshed artifact is a directed OSMnx `MultiDiGraph`. All 17,439 edges have source one-way state, immutable base travel time, length, highway type, access-restriction state, and an explicit turn-restriction support marker. The 8 explicit OSM `access` tags remain present; other edges retain the OSMnx drive-network filter provenance.
- Base routing remains available with no TomTom key or usable snapshot. No turn-restriction compliance is claimed: graph and provenance state `NOT_PROCESSED_OR_VALIDATED`.

TomTom runtime:

- **PASS.** The API key is environment-only. Flow requests use fixed style `absolute`, zoom `22`, units `kmph`, and OpenLR request metadata. Strict parsing rejects missing, malformed, non-finite, out-of-range, or structurally invalid values without filling missing traffic facts.
- `TOMTOM_REFRESH_TIMEOUT_SECONDS = 10` is one total monotonic budget shared by the complete corridor refresh. Tests prove request awaiting stops at budget exhaustion during a multi-observation refresh. There is no immediate retry and failed results are cached for the locked 60-second interval.
- Partial observations can be published only through the same schema, configuration, graph-fingerprint, matching, and snapshot-consistency gates as complete results.

Traffic matching:

- **PASS.** Matching is limited to named Nasr City MVP corridor edges derived from Rabaa, Tayaran, Abbas El Akkad, Makram Ebeid, and El Nasr Road samples.
- Gates are provider confidence at least `0.80`, geometry separation at most `30 m`, and directed bearing difference at most `30 degrees`. Remaining candidates must form one connected, directed, non-branching chain with no competing parallel keys or competing observations. Failed or ambiguous candidates remain unmatched; no extra numerical ambiguity policy was introduced.
- Fixed Flow Segment style/zoom/units are stored on each snapshot. OpenLR is retained only as provider metadata and is not exposed publicly or used as an authoritative location.

Traffic-aware routing:

- **PASS.** `base_eta` is calculated independently on immutable base-optimal weights. `effective_eta` is calculated independently on the captured overlay. `traffic_selected_path_base_eta` separately reports the base-weight cost of the traffic-selected path; legacy `eta_seconds` equals `effective_eta`.
- `TOMTOM_TRAFFIC_ADJUSTED` is emitted only when a validated overlay changes a relevant edge weight or a validated closure changes path selection. A closed edge is unavailable even when it is absent from the selected path. If validated closures leave no feasible path, routing fails explicitly instead of crossing the closure.
- Mixed routing is supported. Matched traversed-edge count is explicit, and primary coverage is matched traversed-edge length divided by total selected-route length. At most one structurally edge-disjoint alternative is returned without inventing an overlap threshold.

Freshness/provenance:

- **PASS.** Locked boundaries are covered exactly: LIVE at 0–60 seconds inclusive, FRESH above 60 through 120 seconds inclusive, and STALE above 120 seconds. Only LIVE/FRESH overlays may affect routing.
- Snapshot `retrieved_at` is local retrieval time. `provider_last_updated` remains null unless the provider supplies an explicit validated update timestamp; local retrieval time is never relabeled as provider time. Freshness uses validated provider time when present, otherwise retrieval time.
- Snapshot ID/version, graph fingerprint, sample-point fingerprint, source/reference, fixed request configuration, provider state, timestamps, freshness, observations/matches, and overlay are captured consistently. `REAL_LIVE` is set only after actual provider data retrieval.

Fallback behavior:

- **PASS.** Missing key, timeout, rate limit, provider outage, malformed payload, stale state, unmatched/ambiguous observations, configuration mismatch, and graph-fingerprint mismatch all remain visible and do not fabricate traffic speed, congestion, closure, or ETA.
- Stale snapshots remain observable but cannot influence routing. A missing/unusable snapshot returns independently computed `OSM_BASE_TRAVEL_TIME`, zero applied traffic coverage, and a specific fallback reason.

API contracts:

- **PASS.** The existing `POST /api/v1/routes/preview` request is unchanged and its response now includes independent ETA fields, selected edge keys, snapshot identity/freshness, matched count, length coverage, materiality flags, fallback reason, and optional edge-disjoint alternative.
- New `GET /api/v1/traffic/snapshot` is read-only. It exposes sanitized provider state, distinct timestamps, freshness, source reference, fixed configuration, observation/match/overlay counts, and the locked prototype thresholds. It does not expose the API key, raw OpenLR, raw observations, or a refresh command.
- Existing map endpoints return artifact-specific provenance rather than attributing all layers to one source. Phase 01 planning remains base-only and was not retrofitted with TomTom behavior.

Tests:

- **PASS — 194 passed**, with 5 existing non-blocking Starlette deprecation warnings.
- Coverage includes exact 60/120-second freshness boundaries; 10-second total-budget exhaustion; no retry inside 60 seconds; strict provider parsing; partial/malformed/rate-limit/outage states; all matching gates and structural ambiguity; graph/snapshot mismatch; stale/missing/unmatched fallback; closure and weight materiality; independent ETA semantics; length-weighted coverage; edge-disjoint alternatives; base-graph immutability; concurrent refresh coalescing; sanitized APIs; fail-closed refresh publication; refreshed real assets; Phase 01 routing; and Golden Flow.

Ruff:

- **PASS.** `python -m ruff check app scripts tests` completed with no findings. Final repository-wide Ruff verification is recorded below before the review commit.

Compile:

- **PASS.** `python -m compileall app scripts tests` completed successfully. Final repository-path compile verification is recorded below before the review commit.

Live smoke:

- **PASS with visible TomTom fallback.** A one-worker Uvicorn smoke returned health 200 and route 200 on a graph-derived Rabaa-to-El-Nasr corridor request. The provider was unavailable, so no live traffic was claimed: routing source remained `OSM_BASE_TRAVEL_TIME`; `base_eta`, `effective_eta`, and selected-path base ETA were all `184.13306275184888`; matched count and coverage were zero; and the failure was `TOMTOM_PROVIDER_UNAVAILABLE`.
- The sanitized snapshot was version 1 with state `UNAVAILABLE`, freshness `UNKNOWN`, style `absolute`, zoom `22`, zero observations/matches/overlay entries, and null retrieval/provider timestamps. A follow-up route inside the cache interval retained the same snapshot ID/version, proving no immediate retry.
- **Golden Flow PASS.** On a separate one-worker process and temporary SQLite database: 7 resources seeded; health 200; manual incident 201; plan 201 with both routes and metrics labeled `OSM_BASE_TRAVEL_TIME`; approval used returned incident version 2 and returned 200/`RESPONSE_ACTIVE` incident version 3; both resources became `ASSIGNED` version 2; repeat approval returned 409 `PLAN_ALREADY_APPROVED`.

Repo reconnaissance:

- Current SirenGrid Phase 01 routing/map implementation, schemas, tests, processed assets, and provenance were inspected before non-trivial implementation.
- Relevant references: authoritative SirenGrid plans/decisions; pinned `MahmoudNagiubX/Egypt-Smart-City-Digital-Twin` commit `93ca9e90e2fc52c914dd5ccbe42bdc84ce745d3d`; official OSMnx 2.1 documentation; official TomTom Flow Segment/Traffic Flow documentation; and TomTom OpenLR reference repositories.
- Reused: retained donor boundary/grid; established OSMnx graph acquisition, speed/travel-time enrichment, GraphML export, and feature extraction patterns; existing SirenGrid loader, snapping, geometry, and map APIs.
- Adapted: preprocessing became staged, hash-validated, provenance-producing, and rollback-safe; routing was refactored behind its existing Phase 01 wrapper to accept a frozen optional overlay without writing graph weights.
- Rejected: donor weather weighting, synthetic/default routes, zero route metrics, silent bounding-box authority, full citywide/OpenLR dereferencing, OpenRouteService, Redis/queues/distributed locks, and all Phase 03+ work.

Real-vs-simulated audit:

- **PASS.** Refreshed OSM artifacts are `REAL_DERIVED`/`STATIC` with `FRESH` acquisition metadata; their physical source features are public OSM facts. Traffic signals explicitly state `NOT_AVAILABLE_FROM_OSM` for operational state. No live signal state or hospital load/capacity is claimed.
- TomTom data can become `REAL_LIVE` only after successful validated retrieval. The live smoke produced no such label. Phase 01 manual incidents and resource state remain explicitly `SIMULATED`; Phase 01 plan routes remain real OSM base calculations.

Secrets audit:

- **PASS.** No local `.env` was read or printed. Tracked environment examples contain blank placeholders only. The TomTom key is excluded from settings serialization and never appears in snapshot/provenance/API schemas, failure details, or request source references.
- Credential-pattern searches found only configuration field names, blank examples, documentation search examples, and the intentional test sentinel `test-secret-must-not-escape`; no credential or private key is committed.

Base-graph mutation audit:

- **PASS.** Matching computes projected geometry and fingerprints without assigning graph attributes. Overlay construction creates frozen edge-key records. Traffic routing reads base weights through callbacks and removes edges only from a copied graph when seeking an alternative.
- Regression tests compare full `node_link_data` and graph fingerprints before/after matching and routing. The refreshed artifact hash also matches its provenance manifest after all live smokes.

Not implemented:

- AI structured extraction, ASR/image production flow, report fusion, coverage optimization, response-planning redesign, hospital scoring/pre-alert, corridor preemption, signal actuation, driver alerts, WebSocket operations, resource movement simulation, dynamic replanning, multi-incident optimization, frontend implementation, and all Phase 03+ behavior.

Decisions requested from owner:

- None. Freshness, matching gates, fixed style/zoom, direct OSMnx acquisition, closure materiality, ETA semantics, coverage ratio, and total timeout were all owner-approved before implementation.

Deviations:

- Direct bounded OSMnx/Overpass acquisition was used instead of making a Geofabrik extract mandatory, exactly as the owner-approved Phase 02 decision permits and the design/provenance records.
- The live TomTom provider did not return usable data during final smoke. The required fail-visible base fallback worked; no retry or live-data claim was made. Provider unavailability does not block Phase 02 because deterministic base routing and all overlay behavior are validated locally.

Blocking issues:

- None identified.

Verdict: PASS

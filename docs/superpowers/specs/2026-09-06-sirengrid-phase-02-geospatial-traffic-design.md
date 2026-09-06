# SirenGrid Phase 02 Geospatial and Traffic Design

Date: 2026-09-06  
Status: Owner-approved with review revisions incorporated
Scope: Phase 02 only

## Objective

Build the Nasr City geospatial and TomTom traffic runtime used by route previews while preserving the real OpenStreetMap base graph as immutable operational truth. Traffic is a versioned, expiring overlay. Provider failure, stale data, malformed data, or uncertain matching must leave base routing available and visibly labeled `OSM_BASE_TRAVEL_TIME`.

This phase does not implement Phase 03 or later behavior.

## Locked Inputs and Policies

### Base data

- Owner-approved Phase 02 implementation decision: use bounded direct OSMnx/Overpass acquisition for the Nasr City MVP road graph. Geofabrik Egypt remains an approved reproducibility/fallback source rather than the mandatory direct acquisition path for this phase.
- Refresh the Phase 01 bootstrap graph from current OpenStreetMap data using that bounded OSMnx/Overpass workflow.
- Preserve source-represented directionality, one-way state, and access restrictions.
- Add base speed and travel-time attributes using OSMnx's documented processing.
- Do not claim turn-restriction compliance. Record `turn_restriction_support_status = NOT_PROCESSED_OR_VALIDATED`.
- A failed refresh must not replace the last validated graph or create synthetic fallback data.

### Traffic freshness

- Refresh/cache interval: 60 seconds.
- `LIVE`: age from 0 through 60 seconds inclusive.
- `FRESH`: age greater than 60 through 120 seconds inclusive.
- `STALE`: age greater than 120 seconds.
- `LIVE` and `FRESH` snapshots may be used when matching succeeds.
- `STALE` snapshots remain observable but cannot affect routing.

### Prototype refresh timeout

- `TOMTOM_REFRESH_TIMEOUT_SECONDS = 10`.
- The 10 seconds are one total budget shared by the complete multi-observation corridor refresh, not a per-request timeout.
- One monotonic deadline governs the cycle. The client stops issuing or awaiting remaining provider requests when that deadline is exhausted.
- Timeout or provider failure is not retried immediately and remains subject to the 60-second refresh/cache interval.
- Partial observations may become usable only when each independently passes schema, freshness, confidence, geometry, direction, ambiguity, graph-fingerprint, and snapshot-consistency validation. Other partial data may remain observable but cannot affect routing.
- This value is a SirenGrid prototype runtime timeout, not a TomTom quota, SLA, or emergency dispatch standard.

### Prototype matching safety gates

These are SirenGrid prototype safety thresholds, not official TomTom dispatch thresholds:

- TomTom provider confidence must be at least `0.80`.
- Geometry separation must be at most `30` meters.
- Direction difference must be at most `30` degrees.
- A failed confidence, geometry, direction, or ambiguity check produces `UNMATCHED`.
- No additional numerical ambiguity threshold is permitted without another owner decision.

### Fixed TomTom request geometry

All Flow Segment observations use one explicit configuration:

- style: `absolute`
- zoom: `22`
- units: `kmph`
- OpenLR requested: `true`, retained as provider metadata but not used as authority in the prototype matcher

These values are configuration constants. The snapshot records style and zoom so observations produced under different geometry settings cannot be silently mixed. Zoom 22 is selected because TomTom documents that returned coordinates are shifted according to zoom; using one fixed maximum supported zoom minimizes display-oriented displacement and makes matching reproducible.

## Architecture

### 1. Immutable base graph

The runtime loads one directed OSM `MultiDiGraph`. Route calculation may read topology, geometry, `length`, `speed_kph`, `travel_time`, `oneway`, and `access`, but traffic code never writes edge attributes or removes graph edges.

A deterministic graph fingerprint is calculated from the validated artifact and included in provenance. Each route calculation captures both a base-graph reference and one traffic snapshot reference before pathfinding starts.

### 2. Reproducible geospatial refresh

A bounded preprocessing command:

1. Loads the existing real Nasr City boundary.
2. requests the current drivable OSM network for that polygon;
3. adds edge speeds and base travel times;
4. validates graph type, CRS, non-empty topology, numeric positive lengths/travel times, and retained one-way/access fields;
5. extracts OSM traffic signals and approved emergency-facility features;
6. exports GraphML and frontend-ready GeoJSON to a temporary staging directory;
7. writes artifact hashes, record counts, source URLs/query definitions, retrieval timestamp, and reality/freshness labels;
8. replaces committed processed artifacts only after every validation passes.

Graph and infrastructure artifacts are `REAL_DERIVED`. Their underlying source is `REAL_PUBLIC`. They are `STATIC` operational inputs even when freshly downloaded; their provenance records the actual retrieval time rather than claiming live status. Existing 500-meter operational zones remain unchanged except for validation against the refreshed boundary.

Direct OSMnx/Overpass acquisition for the bounded Nasr City MVP graph is an explicit owner-approved Phase 02 implementation decision. Geofabrik Egypt remains an approved reproducibility/fallback source. This resolves the earlier Geofabrik-oriented processing language without changing the requirement that every produced artifact identify its actual direct source. The provenance document retains the approved Geofabrik reference and states whether direct Overpass acquisition or a separately executed Geofabrik workflow produced each artifact. A failed acquisition or validation preserves the last validated real graph unchanged.

### 3. TomTom client and snapshot cache

The TomTom client reads `TOMTOM_API_KEY` only from environment-backed settings. It calls Flow Segment Data for bounded, configured corridor/route sample points. Provider payloads are untrusted and must pass strict schema and value validation before becoming observations.

An immutable snapshot contains:

- snapshot ID/version;
- source and source reference;
- local `retrieved_at` and an optional provider-originated `provider_last_updated` timestamp;
- freshness status;
- data reality (`REAL_LIVE` only after a successful real retrieval);
- graph fingerprint;
- fixed style, zoom, and units;
- validated observations;
- matched and unmatched results with reasons;
- provider/error state without secrets;
- matched-edge count and observation counts.

The cache permits at most one provider refresh attempt in each 60-second interval, including failed attempts. Route preview may request a refresh when no cached attempt exists in the interval, then uses the captured result or falls back. One monotonic deadline limits the complete refresh to 10 seconds; every provider request receives only the budget remaining at issue time, and no further request is issued after exhaustion. This prevents request-driven retry loops without inventing provider quota values.

Missing credentials, timeout, rate limiting, non-success status, malformed JSON, invalid values, or partial unusable responses produce an observable unavailable/malformed snapshot state and base-route fallback. Provider response bodies and API keys are not logged.

Freshness age is measured from local `retrieved_at` unless TomTom supplies an explicit provider update timestamp that passes parsing and temporal validation. Only then may `provider_last_updated` be populated and used as the freshness origin. Local retrieval time is never presented as provider-originated `last_updated`, and the runtime never fabricates a provider timestamp.

### 4. Corridor-first matching without a new ambiguity threshold

The primary matching scope is the configured Rabaa → Tayaran → Abbas El Akkad → Makram Ebeid → El Nasr Road corridor and route-relevant edges within that scope.

Each TomTom observation geometry is projected into the graph's local metric CRS. Candidate directed OSM edges are those in the bounded corridor/route scope whose geometry is no more than 30 meters from the observation. Candidates are then filtered by the 30-degree directed-bearing gate. Provider confidence is checked first.

Passing candidate edges must form exactly one contiguous, non-branching directed chain. Zero candidate chains is unmatched. More than one chain, a branch, or competing parallel candidates is ambiguous and therefore unmatched. This is a structural ambiguity rule, not an additional numerical threshold. All edges in the single accepted chain receive the same validated observation reference in the overlay.

TomTom coordinates never alter OSM geometry or topology. OpenLR is retained for audit/debugging only; Phase 02 does not introduce a full OpenLR dereferencing platform.

### 5. Traffic overlay and effective routing weight

The overlay is an immutable mapping keyed by `(u, v, key)` and tied to one graph fingerprint and snapshot version. It contains observation references, provider values, matching results, and closure state. It never mutates the graph.

For a matched, usable observation:

- a provider-reported road closure makes that edge unavailable only to the traffic-aware calculation;
- otherwise the edge weight is `base_travel_time * (current_travel_time / free_flow_travel_time)`;
- current and free-flow travel times must both be finite and strictly positive;
- no invented speed, congestion, ETA, clamp, or default factor is allowed.

Unmatched edges use their unchanged base travel time. The selected route is labeled `TOMTOM_TRAFFIC_ADJUSTED` only when the validated overlay materially affects routing by either:

- changing the weight of at least one edge traversed by the selected traffic-aware route; or
- making a matched edge unavailable through a validated TomTom road closure and thereby changing path selection.

A closure affects path selection when a validated closed edge occurs on the independently calculated base-optimal path and the traffic-aware path avoids it. Such a result remains `TOMTOM_TRAFFIC_ADJUSTED` even though the closed edge is not traversed. A usable observation or closure elsewhere that does not affect either selected-path weights or path selection does not change the route label.

The response exposes:

- `base_eta`, calculated from the independently selected base-optimal route using immutable base weights;
- `effective_eta`, calculated for the independently selected traffic-aware route using the captured overlay;
- routing source;
- snapshot ID/version and freshness when a snapshot was considered;
- matched traversed-edge count;
- total traversed-edge count;
- traffic coverage ratio, calculated as the sum of traffic-covered traversed-edge lengths divided by total traversed route length;
- explicit fallback reason when traffic was not applied.

The base route and traffic-aware route are computed independently. `base_eta` always means the ETA of the base-optimal route under immutable OSM weights. `effective_eta` means the ETA of the selected traffic-aware route under the captured overlay. If the base-weight cost of the traffic-selected path is exposed for explanation, its field is `traffic_selected_path_base_eta`, never `base_eta`. A traffic-adjusted route may differ from the base path. Phase 02 may return one meaningfully distinct alternative when the graph provides one, but it does not create future-phase replanning behavior.

### 6. Minimum API contracts

- Extend the existing route-preview contract; do not create a parallel routing subsystem.
- Add one read-only traffic snapshot/state endpoint for provenance, freshness, matching counts, configuration metadata, and provider state.
- Do not add a public manual-refresh endpoint. Route preview owns the bounded refresh attempt and the cache enforces the interval.
- Existing map-layer endpoints continue to return base OSM-derived artifacts.

The OpenAPI contract must distinguish `OSM_BASE_TRAVEL_TIME` from `TOMTOM_TRAFFIC_ADJUSTED` and must not imply that stale, unavailable, or unmatched data affected an ETA.

## Error and Fallback Matrix

| Condition | Observable state | Routing behavior |
|---|---|---|
| No API key | unavailable, no secret detail | OSM base |
| Provider timeout/server error | unavailable with sanitized reason | OSM base |
| Total 10-second refresh budget exhausted | timed out/partial with completed observation metadata | only independently valid, snapshot-consistent partial matches may be eligible; otherwise OSM base |
| HTTP 429 | rate-limited | OSM base; no retry inside 60 s |
| Malformed/invalid payload | malformed | OSM base |
| Validated freshness-origin age 0–60 s | LIVE | eligible if matches pass |
| Validated freshness-origin age >60–120 s | FRESH | eligible if matches pass |
| Validated freshness-origin age >120 s | STALE | visible, never applied |
| Confidence <0.80 | unmatched | affected OSM edges remain base |
| Separation >30 m | unmatched | affected OSM edges remain base |
| Direction difference >30° | unmatched | affected OSM edges remain base |
| Multiple/branching candidate chains | unmatched/ambiguous | affected OSM edges remain base |
| Usable overlay outside selected path | snapshot visible | selected route remains base-labeled |
| At least one selected-path edge weight adjusted | usable mixed or full overlay | traffic-adjusted label and length coverage |
| Validated closure changes path selection | closure provenance visible | traffic-adjusted label even though the closed edge is not traversed |

## Testing Strategy

Behavioral work follows focused red-green-refactor cycles. Provider tests use deterministic HTTP fakes and never consume quota.

Required automated coverage:

- freshness boundaries at exactly 60 and 120 seconds, and immediately above each;
- local retrieval versus validated provider update timestamp semantics, including rejection of fabricated/future provider timestamps;
- fixed `absolute`/zoom `22` request construction and recorded metadata;
- valid and malformed Flow Segment parsing;
- rate-limit, timeout, server-error, missing-key, and failed-attempt cache behavior;
- one monotonic 10-second total deadline across a multi-observation refresh, including exhaustion before all requests are issued;
- successful confidence/geometry/direction match;
- each failed safety gate;
- structural ambiguity and unmatched observations;
- stale snapshot visibility and routing exclusion;
- mixed-state adjustment and length-weighted coverage ratio;
- traffic label only when a selected edge weight was adjusted or a validated closure changed path selection;
- independent base-optimal `base_eta` and overlay-optimal `effective_eta` calculations;
- closure handling in overlay-only routing;
- graph fingerprint mismatch fallback;
- base graph attribute/topology fingerprint unchanged before and after traffic routing;
- refreshed GraphML/GeoJSON validation and provenance labels;
- existing Phase 01 base-routing and Golden Flow regression coverage.

Final verification includes full pytest, Ruff, compileall, a one-worker live Golden Flow smoke, a TomTom live smoke when the key/provider are available, provenance/reality audit, secret audit, and base-graph mutation audit.

## Repository Reconnaissance Record

Repo reconnaissance performed:

- Current SirenGrid Phase 01 routing, map APIs, schemas, tests, processed assets, and provenance.
- `MahmoudNagiubX/Egypt-Smart-City-Digital-Twin` at pinned commit `93ca9e90e2fc52c914dd5ccbe42bdc84ce745d3d`.
- Official OSMnx 2.1 documentation and implementation references.
- Official TomTom Flow Segment Data and Traffic Flow documentation.
- TomTom's OpenLR decoder/dereferencer reference repositories.

Relevant references:

- https://osmnx.readthedocs.io/en/stable/user-reference.html
- https://docs.tomtom.com/traffic-api/documentation/tomtom-maps/v1/traffic-flow/flow-segment-data
- https://docs.tomtom.com/traffic-api/documentation/tomtom-maps/v1/traffic-flow/traffic-flow-service
- https://github.com/tomtom-international/openlr-python
- https://github.com/tomtom-international/openlr-dereferencer-python

What is reused:

- Donor graph acquisition, OSMnx speed/travel-time enrichment, GraphML export, and feature-extraction patterns.
- Existing SirenGrid graph loader, snapping, route geometry, and map endpoints.

What is adapted:

- Donor preprocessing becomes fail-closed, staged, validated, and provenance-producing.
- Existing base routing accepts an immutable optional traffic snapshot rather than writing weights into the graph.

What is rejected and why:

- Donor weather-specific risk weighting: outside scope and mutates graph weights.
- Donor synthetic/default route fallback and zero route metrics: would fabricate operational facts.
- Silent bounding-box fallback as authoritative boundary: violates provenance requirements.
- Full OpenLR dereferencing/citywide matching: excessive for the corridor-first MVP.
- OpenRouteService, PostGIS expansion, Redis, queues, distributed locks, frontend work, and Phase 03+ behavior: outside Phase 02.

## Implementation Increments

1. Lock configuration, freshness evaluation, snapshot models, and boundary tests.
2. Add strict TomTom parsing/client/cache behavior with provider-failure tests.
3. Implement corridor-first matcher and immutable overlay with safety-gate tests.
4. Extend routing and schemas for base/traffic-aware mixed routing and integrity tests.
5. Extend the minimum API contracts and keep Golden Flow passing.
6. Add and run the staged geospatial refresh pipeline; validate and commit refreshed artifacts and provenance.
7. Run live feasibility smoke, complete the Phase 02 review, and commit the reviewed result.

## Strictly Out of Scope

- AI structured extraction, ASR/image production, and report fusion.
- Coverage optimization and response-planning redesign.
- Hospital scoring/pre-alert.
- Emergency corridor preemption logic, driver alerts, and traffic-signal control.
- WebSocket operations, movement simulation, dynamic replanning, multi-incident optimization, and frontend implementation.
- Phase 03 or later behavior.

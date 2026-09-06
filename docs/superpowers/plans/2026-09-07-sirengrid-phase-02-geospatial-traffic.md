# SirenGrid Phase 02 Geospatial and Traffic Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a current, provenance-backed Nasr City base graph and a fail-closed TomTom traffic overlay that can adjust route previews without mutating OSM truth.

**Architecture:** Keep the directed OSM `MultiDiGraph` immutable and represent every traffic refresh as an immutable, graph-fingerprinted snapshot plus edge-keyed overlay. Compute the OSM-optimal and overlay-optimal routes independently, expose explicit provenance/freshness/coverage, and fall back visibly whenever provider or matching validation fails.

**Tech Stack:** Python 3.12, FastAPI, Pydantic 2, HTTPX, NetworkX, OSMnx 2.x, Shapely, pyproj, GeoPandas, pytest, Ruff.

**Spec:** `docs/superpowers/specs/2026-09-06-sirengrid-phase-02-geospatial-traffic-design.md`

## Global Constraints

- Work only on `feature/phase-01-golden-flow`; do not create another branch or modify/merge `origin/main`.
- Phase 02 only. Do not implement AI extraction, ASR/image production, fusion, coverage, hospital ranking/pre-alert, corridor preemption, driver alerts, WebSocket behavior, movement, replanning, multi-incident optimization, frontend work, or Phase 03 behavior.
- Direct OSMnx/Overpass acquisition is owner-approved for the bounded Nasr City road graph; Geofabrik Egypt remains an approved reproducibility/fallback source.
- Preserve the last validated real graph on every failed acquisition, build, validation, or publication attempt. Never create a synthetic fallback graph.
- Preserve represented one-way/access restrictions. Record turn restrictions as `NOT_PROCESSED_OR_VALIDATED`; never claim compliance.
- TomTom freshness: `LIVE` at 0–60 seconds inclusive, `FRESH` above 60–120 seconds inclusive, `STALE` above 120 seconds and unusable.
- TomTom refresh interval: 60 seconds, including failed attempts.
- TomTom refresh timeout: one 10-second monotonic total budget for the complete corridor refresh, never 10 seconds per observation.
- Fixed Flow Segment configuration: style `absolute`, zoom `22`, units `kmph`, OpenLR requested and retained only as metadata.
- Prototype matching gates: provider confidence at least `0.80`, geometry separation at most `30` meters, direction difference at most `30` degrees.
- Do not add a numerical ambiguity threshold. Passing candidates must form exactly one contiguous, non-branching directed chain; otherwise the observation is unmatched.
- Partial results are usable only observation-by-observation after all schema, freshness, matching, graph-fingerprint, and snapshot-consistency checks pass.
- Traffic is an immutable overlay. No traffic operation may alter base graph nodes, edges, or attributes.
- `TOMTOM_TRAFFIC_ADJUSTED` requires a traversed weight change or a validated closure that changes path selection.
- `base_eta` is the independently computed OSM-optimal ETA; `effective_eta` is the independently computed overlay-optimal ETA.
- Traffic coverage is covered traversed-edge length divided by total selected-route length, not an edge-count ratio.
- API keys remain environment-only and must never appear in logs, exceptions, test fixtures, snapshots, provenance, diffs, or commits.
- Behavioral tasks use focused RED → GREEN → REFACTOR. Run the full suite before each logical commit and final review.

## File Structure

### Runtime modules

- `backend/app/traffic/models.py`: frozen traffic observation, match, overlay, snapshot, and provider-state types.
- `backend/app/traffic/freshness.py`: timestamp validation and exact 60/120-second freshness policy.
- `backend/app/traffic/client.py`: strict Flow Segment parsing and one-deadline multi-point HTTP acquisition.
- `backend/app/traffic/matching.py`: corridor edge selection and structural confidence-aware geometry matching.
- `backend/app/traffic/runtime.py`: refresh cache, snapshot creation, graph binding, and sanitized fallback state.
- `backend/app/traffic/api.py`: read-only current-snapshot endpoint.
- `backend/app/routing.py`: reusable path/edge calculation and independent base/overlay routing.
- `backend/app/map.py`: route-preview orchestration using one captured snapshot.
- `backend/app/schemas.py`: minimum public traffic and route-preview contracts.
- `backend/app/config.py`: explicit Phase 02 constants and environment-backed secret.

### Data tooling and artifacts

- `backend/scripts/refresh_nasr_city_geospatial.py`: staged OSMnx/Overpass acquisition, validation, export, provenance, and rollback-safe publication.
- `data/processed/nasr_city/nasr_city_traffic_signals.geojson`: current OSM-derived signal locations.
- `data/processed/nasr_city/nasr_city_traffic_sample_points.geojson`: five bounded corridor observation points derived from the refreshed OSM graph.
- Existing graph, boundary, emergency-facility, and provenance artifacts: validated refresh output.

### Tests

- `backend/tests/test_traffic_freshness.py`
- `backend/tests/test_tomtom_client.py`
- `backend/tests/test_traffic_matching.py`
- `backend/tests/test_traffic_runtime.py`
- `backend/tests/test_traffic_routing.py`
- `backend/tests/test_geospatial_refresh.py`
- Existing routing, map, contract, asset, and Golden Flow tests: extended only where public contracts intentionally change.

---

### Task 1: Lock configuration, snapshot types, and freshness semantics

**Files:**
- Modify: `backend/app/config.py`
- Modify: `backend/.env.example`
- Create: `backend/app/traffic/__init__.py`
- Create: `backend/app/traffic/models.py`
- Create: `backend/app/traffic/freshness.py`
- Create: `backend/tests/test_traffic_freshness.py`

**Interfaces:**
- Produces: `TrafficProviderState`, `TrafficMatchStatus`, `EdgeKey`, `TrafficObservation`, `TrafficEdgeMatch`, `TrafficOverlay`, `TrafficSnapshot`.
- Produces: `evaluate_freshness(snapshot, now) -> FreshnessStatus` and `freshness_origin(snapshot) -> datetime | None`.
- Produces settings properties for the API key, 60/120-second policy, 10-second total budget, `absolute`, zoom `22`, `kmph`, confidence `0.80`, distance `30`, and direction `30`.

- [ ] **Step 1: Write failing settings and boundary tests**

```python
def test_phase02_tomtom_defaults_are_explicit():
    assert settings.TOMTOM_REFRESH_INTERVAL_SECONDS == 60
    assert settings.TOMTOM_FRESH_MAX_AGE_SECONDS == 120
    assert settings.TOMTOM_REFRESH_TIMEOUT_SECONDS == 10
    assert settings.TOMTOM_FLOW_STYLE == "absolute"
    assert settings.TOMTOM_FLOW_ZOOM == 22
    assert settings.TOMTOM_FLOW_UNITS == "kmph"
    assert settings.TOMTOM_MIN_PROVIDER_CONFIDENCE == 0.80
    assert settings.TOMTOM_MAX_GEOMETRY_SEPARATION_M == 30
    assert settings.TOMTOM_MAX_DIRECTION_DIFFERENCE_DEGREES == 30

@pytest.mark.parametrize(
    ("age_seconds", "expected"),
    [(0, FreshnessStatus.LIVE), (60, FreshnessStatus.LIVE),
     (60.001, FreshnessStatus.FRESH), (120, FreshnessStatus.FRESH),
     (120.001, FreshnessStatus.STALE)],
)
def test_freshness_boundaries(age_seconds, expected):
    now = datetime(2026, 9, 7, tzinfo=timezone.utc)
    snapshot = make_snapshot(retrieved_at=now - timedelta(seconds=age_seconds))
    assert evaluate_freshness(snapshot, now) is expected
```

- [ ] **Step 2: Run RED**

Run: `cd backend; python -m pytest tests/test_traffic_freshness.py -q`  
Expected: FAIL because the traffic package and settings do not exist.

- [ ] **Step 3: Add exact settings and frozen models**

Add Pydantic fields to `Settings` and environment loading without ever serializing `tomtom_api_key`. In `models.py`, use frozen Pydantic models and explicit enums. The central snapshot shape must include these fields:

```python
class TrafficSnapshot(BaseModel):
    model_config = ConfigDict(frozen=True)
    snapshot_id: str
    version: int = Field(gt=0)
    graph_fingerprint: str
    provider_state: TrafficProviderState
    refresh_attempted_at: datetime
    retrieved_at: datetime | None = None
    provider_last_updated: datetime | None = None
    freshness_status: FreshnessStatus
    source: str
    source_reference: str
    data_reality: DataReality | None = None
    flow_style: str
    flow_zoom: int
    units: str
    observations: tuple[TrafficObservation, ...] = ()
    matches: tuple[TrafficEdgeMatch, ...] = ()
    overlay: TrafficOverlay | None = None
    failure_reason: str | None = None
```

Every observation records its local response-receipt time. Snapshot `retrieved_at` is the earliest retrieval time among usable observations. A failed attempt with no retrieved observation has `retrieved_at=None`, `data_reality=None`, and `UNKNOWN` freshness. `freshness_origin` may use `provider_last_updated` only when it is timezone-aware and not later than `retrieved_at`; otherwise the model validator rejects it. `evaluate_freshness` rejects a `now` earlier than the origin instead of converting negative age to LIVE.

Represent `TrafficOverlay.entries` as a deterministically sorted tuple of frozen `TrafficOverlayEntry` values, not a mutable dictionary. Provide a read-only `entry_for(edge_key)` lookup so callers cannot mutate snapshot state through nested containers.

- [ ] **Step 4: Update `.env.example` with non-secret explicit runtime values**

```dotenv
TOMTOM_REFRESH_INTERVAL_SECONDS=60
TOMTOM_FRESH_MAX_AGE_SECONDS=120
TOMTOM_REFRESH_TIMEOUT_SECONDS=10
TOMTOM_FLOW_STYLE=absolute
TOMTOM_FLOW_ZOOM=22
TOMTOM_FLOW_UNITS=kmph
TOMTOM_MIN_PROVIDER_CONFIDENCE=0.80
TOMTOM_MAX_GEOMETRY_SEPARATION_M=30
TOMTOM_MAX_DIRECTION_DIFFERENCE_DEGREES=30
```

- [ ] **Step 5: Run GREEN and the existing configuration/schema tests**

Run: `cd backend; python -m pytest tests/test_traffic_freshness.py tests/test_schemas.py tests/test_contracts.py -q`  
Expected: PASS.

- [ ] **Step 6: Run the full suite, review the diff, and commit**

Run: `cd backend; python -m pytest -q`  
Run: `cd backend; python -m ruff check app tests`  
Commit: `git commit -m "feat: define Phase 02 traffic snapshot policy"`

---

### Task 2: Implement strict TomTom parsing and the total refresh deadline

**Files:**
- Create: `backend/app/traffic/client.py`
- Create: `backend/tests/test_tomtom_client.py`

**Interfaces:**
- Consumes: Phase 02 settings and `TrafficObservation`.
- Produces: `CorridorSamplePoint`, `TomTomRefreshResult`, `TomTomFlowClient.refresh(points, *, refresh_attempted_at, wall_clock, monotonic) -> TomTomRefreshResult`.
- `TomTomFlowClient` accepts an `httpx.Client`, UTC wall-clock callable, and monotonic callable for deterministic tests. Wall-clock values label provider receipt; only monotonic values enforce the budget.

- [ ] **Step 1: Write failing payload-validation tests**

```python
def test_parse_flow_segment_accepts_documented_payload():
    observation = parse_flow_segment(
        payload={"flowSegmentData": {
            "frc": "FRC2", "currentSpeed": 41, "freeFlowSpeed": 70,
            "currentTravelTime": 153, "freeFlowTravelTime": 90,
            "confidence": 0.80, "roadClosure": False,
            "coordinates": {"coordinate": [
                {"latitude": 30.07, "longitude": 31.33},
                {"latitude": 30.06, "longitude": 31.34},
            ]}, "openlr": "audit-only"}},
        sample=sample_point,
    )
    assert observation.confidence == 0.80
    assert observation.coordinates[0] == (31.33, 30.07)

@pytest.mark.parametrize("field,value", [
    ("currentTravelTime", 0), ("freeFlowTravelTime", -1),
    ("confidence", 1.1), ("coordinates", {"coordinate": []}),
])
def test_parse_flow_segment_rejects_invalid_operational_values(field, value):
    with pytest.raises(TomTomPayloadError):
        parse_flow_segment(payload_with(field, value), sample_point)
```

- [ ] **Step 2: Write failing request-contract and total-budget tests**

The fake HTTP client records each URL, params, and `timeout`. A monotonic sequence reaches the shared deadline during a three-point attempt:

```python
def test_refresh_uses_fixed_style_zoom_and_one_total_deadline():
    clock = SequenceClock([100.0, 101.0, 106.0, 110.0])
    result = client.refresh(
        three_samples,
        refresh_attempted_at=NOW,
        wall_clock=utc_clock,
        monotonic=clock,
    )
    assert fake_http.request_count == 2
    assert fake_http.calls[0].path.endswith("/absolute/22/json")
    assert fake_http.calls[0].params["unit"] == "kmph"
    assert fake_http.calls[0].params["openLr"] == "true"
    assert fake_http.calls[0].timeout == pytest.approx(9.0)
    assert fake_http.calls[1].timeout == pytest.approx(4.0)
    assert result.state is TrafficProviderState.TIMED_OUT
    assert result.completed_observation_count == 2
```

Also assert no third request, no retry, no key in recorded source references/errors, 429 stops the cycle, and valid completed observations remain distinguishable from incomplete/unusable state.

- [ ] **Step 3: Run RED**

Run: `cd backend; python -m pytest tests/test_tomtom_client.py -q`  
Expected: FAIL because the client does not exist.

- [ ] **Step 4: Implement strict parsing and one monotonic deadline**

Use one deadline and compute the HTTP timeout from the remaining total budget before every call:

```python
deadline = monotonic() + settings.TOMTOM_REFRESH_TIMEOUT_SECONDS
for sample in points:
    remaining = deadline - monotonic()
    if remaining <= 0:
        return partial_result(TrafficProviderState.TIMED_OUT)
    response = http.get(build_url(), params=safe_params(sample), timeout=remaining)
```

After each successful response, stamp that observation with the injected UTC wall clock. Abort on timeout, 429, or server/provider error; do not retry. Validate each payload independently. Never preserve provider response bodies in errors. A partial result contains only already validated observations and explicit completion/failure counts.

- [ ] **Step 5: Run GREEN and Ruff**

Run: `cd backend; python -m pytest tests/test_tomtom_client.py tests/test_traffic_freshness.py -q`  
Run: `cd backend; python -m ruff check app/traffic tests/test_tomtom_client.py`  
Expected: PASS.

- [ ] **Step 6: Run the full suite, inspect for secret leakage, and commit**

Run: `cd backend; python -m pytest -q`  
Run: `git diff --check`  
Run: `rg -n "apiKey=|TOMTOM_API_KEY=.+" backend data docs --glob "!backend/.env"`  
Commit: `git commit -m "feat: add bounded TomTom flow client"`

---

### Task 3: Implement corridor-first matching and immutable overlays

**Files:**
- Create: `backend/app/traffic/matching.py`
- Create: `backend/tests/test_traffic_matching.py`

**Interfaces:**
- Consumes: `TrafficObservation`, `EdgeKey`, `TrafficEdgeMatch`, `TrafficOverlay`.
- Produces: `graph_fingerprint(graph) -> str`.
- Produces: `select_corridor_edges(graph, corridor_names) -> frozenset[EdgeKey]`.
- Produces: `match_observation(graph, observation, allowed_edges) -> TrafficEdgeMatch`.
- Produces: `build_overlay(graph, snapshot_id, observations, allowed_edges) -> TrafficOverlay`.

- [ ] **Step 1: Write failing gate and ambiguity tests using small metric fixtures**

Create deterministic WGS84 graph fixtures with directed edge geometries. Tests must prove:

```python
def test_observation_matching_all_gates_produces_one_chain():
    match = match_observation(graph, valid_observation, allowed_edges)
    assert match.status is TrafficMatchStatus.MATCHED
    assert match.edge_keys == (("a", "b", "0"), ("b", "c", "0"))
    assert match.max_geometry_separation_m <= 30
    assert match.max_direction_difference_degrees <= 30

@pytest.mark.parametrize("observation,reason", [
    (confidence_079, "LOW_PROVIDER_CONFIDENCE"),
    (geometry_just_over_30m, "GEOMETRY_SEPARATION"),
    (direction_just_over_30deg, "DIRECTION_DIFFERENCE"),
])
def test_failed_safety_gate_remains_unmatched(observation, reason):
    result = match_observation(graph, observation, allowed_edges)
    assert result.status is TrafficMatchStatus.UNMATCHED
    assert result.reason == reason
    assert result.edge_keys == ()
```

Add separate tests where candidates form two disconnected chains, branch at an intersection, or compete as parallel keys; each must return `AMBIGUOUS` without a numeric ambiguity margin.

- [ ] **Step 2: Write failing graph-binding and immutability tests**

Capture `node_link_data(graph)` and `graph_fingerprint(graph)` before matching. Build an overlay, then assert exact equality afterward. Assert an overlay built for fingerprint A is rejected against graph B.

- [ ] **Step 3: Run RED**

Run: `cd backend; python -m pytest tests/test_traffic_matching.py -q`  
Expected: FAIL because matching functions do not exist.

- [ ] **Step 4: Implement metric geometry and structural ambiguity checks**

Parse edge WKT or node endpoints into Shapely lines, transform WGS84 geometries into the UTM CRS estimated for the bounded graph extent, and record the CRS identifier in match debug metadata. Filter in this order: provider confidence, 30-meter line separation, 30-degree directed bearing. The remaining directed candidate subgraph must be one weakly connected non-branching chain with no competing parallel keys.

Do not write projected geometry or match values back onto `graph`. Build frozen overlay entries keyed by `(str(u), str(v), str(key))`.

- [ ] **Step 5: Run GREEN and dependency-focused verification**

Run: `cd backend; python -m pytest tests/test_traffic_matching.py -q`  
Run: `cd backend; python -m ruff check app/traffic/matching.py tests/test_traffic_matching.py`  
Expected: PASS.

- [ ] **Step 6: Run the full suite and commit**

Run: `cd backend; python -m pytest -q`  
Commit: `git commit -m "feat: match TomTom observations to immutable OSM overlays"`

---

### Task 4: Add the refresh cache and snapshot-consistency runtime

**Files:**
- Create: `backend/app/traffic/runtime.py`
- Create: `backend/tests/test_traffic_runtime.py`

**Interfaces:**
- Consumes: `TomTomFlowClient`, matcher, freshness policy, graph fingerprint, and corridor sample-point GeoJSON.
- Produces: `TrafficRuntime.capture_snapshot(graph, *, now, wall_clock, monotonic) -> TrafficSnapshot`.
- Produces: `TrafficRuntime.current_snapshot(*, now) -> TrafficSnapshot | None`.
- Produces: module-level `traffic_runtime` configured without exposing the key.

- [ ] **Step 1: Write failing cache and provider-state tests**

```python
def test_failed_refresh_is_not_retried_inside_sixty_seconds():
    first = runtime.capture_snapshot(
        graph, now=T0, wall_clock=utc_clock, monotonic=clock
    )
    second = runtime.capture_snapshot(
        graph,
        now=T0 + timedelta(seconds=59),
        wall_clock=utc_clock,
        monotonic=clock,
    )
    assert first.provider_state is TrafficProviderState.RATE_LIMITED
    assert second.snapshot_id == first.snapshot_id
    assert fake_client.refresh_count == 1

def test_refresh_is_allowed_at_sixty_seconds():
    runtime.capture_snapshot(
        graph, now=T0, wall_clock=utc_clock, monotonic=clock
    )
    runtime.capture_snapshot(
        graph,
        now=T0 + timedelta(seconds=60),
        wall_clock=utc_clock,
        monotonic=clock,
    )
    assert fake_client.refresh_count == 2
```

Cover missing key, missing/malformed sample-point asset, graph fingerprint mismatch, timeout, malformed payload, stale snapshot, and a partial result where exactly one independently valid observation becomes a graph-consistent overlay entry.

- [ ] **Step 2: Run RED**

Run: `cd backend; python -m pytest tests/test_traffic_runtime.py -q`  
Expected: FAIL because `TrafficRuntime` does not exist.

- [ ] **Step 3: Implement lock-protected capture and fail-closed partial handling**

Use a process-local `threading.Lock` so simultaneous route previews cannot launch duplicate refreshes. Capture graph fingerprint, settings, point-set fingerprint, retrieval time, and client result once. Publish the immutable snapshot only after all overlay construction completes. A refresh for graph fingerprint A cannot be returned for graph B.

Snapshot IDs use UUIDs and versions increase monotonically in process. `source_reference` is a non-secret endpoint identifier plus snapshot ID, never a URL query containing the key.

- [ ] **Step 4: Run GREEN and a concurrent cache test**

Add a barrier-based test with two threads calling `capture_snapshot` simultaneously; assert one client refresh and the same immutable snapshot for both callers.

Run: `cd backend; python -m pytest tests/test_traffic_runtime.py -q`  
Expected: PASS.

- [ ] **Step 5: Run the full suite and commit**

Run: `cd backend; python -m pytest -q`  
Run: `cd backend; python -m ruff check app tests`  
Commit: `git commit -m "feat: cache graph-bound traffic snapshots"`

---

### Task 5: Compute independent base and traffic-aware routes

**Files:**
- Modify: `backend/app/routing.py`
- Create: `backend/tests/test_traffic_routing.py`
- Modify: `backend/tests/test_routing.py`

**Interfaces:**
- Consumes: a captured `TrafficSnapshot` whose fingerprint matches the graph.
- Preserves: `compute_route_on_graph(...) -> RouteResult` and its Phase 01 behavior.
- Produces: `compute_traffic_aware_route(graph, origin, destination, snapshot, max_snap_distance_m=None) -> TrafficAwareRouteResult`.
- Produces result fields `base_eta`, `effective_eta`, `traffic_selected_path_base_eta`, `matched_traversed_edge_count`, `total_traversed_edge_count`, `traffic_coverage_ratio`, snapshot metadata, and fallback reason.
- Produces at most one optional edge-disjoint alternative route; no numerical overlap threshold is introduced.

- [ ] **Step 1: Write failing independent-route and weighted-coverage tests**

Build a graph with a 100-meter/10-second direct edge and a two-edge 900-meter/30-second alternate path. Overlay the direct edge with a valid 4x factor. Assert:

```python
result = compute_traffic_aware_route(graph, origin, destination, snapshot)
assert result.base_nodes == ["a", "d"]
assert result.nodes == ["a", "b", "d"]
assert result.base_eta == 10
assert result.effective_eta == 30
assert result.traffic_selected_path_base_eta == 30
assert result.routing_source == "TOMTOM_TRAFFIC_ADJUSTED"
```

For a selected route containing a 100-meter matched edge and a 300-meter unmatched edge, assert coverage is `0.25`, regardless of edge count.

- [ ] **Step 2: Write failing closure-materiality tests**

Assert a validated closure on the base-optimal edge selects the alternate path and labels it `TOMTOM_TRAFFIC_ADJUSTED` even though the closed edge is absent from `result.edge_keys`. Assert a closure outside the base and traffic-selected paths does not change the base label.

Also assert that when validated closures leave no overlay-feasible path, `RouteNotFoundError` is raised rather than routing through a known closed edge.

Add a graph with two edge-disjoint feasible paths and assert one optional alternative is returned. Add a graph whose only other shortest-simple path shares an edge with the primary and assert no alternative is returned. This satisfies the architecture's meaningful-alternative requirement structurally without inventing a numerical overlap threshold.

- [ ] **Step 3: Write failing fallback and immutability tests**

Cover stale, missing, malformed, unmatched, and fingerprint-mismatched snapshots. Each returns the independently computed base route with zero matched length and an explicit fallback reason. Deep-copy `nx.node_link_data(graph, edges="edges")` before and after each traffic-aware calculation and assert equality.

- [ ] **Step 4: Run RED**

Run: `cd backend; python -m pytest tests/test_traffic_routing.py -q`  
Expected: FAIL because traffic-aware routing does not exist.

- [ ] **Step 5: Refactor base path assembly without changing Phase 01 behavior**

Extract a private path calculator that returns deterministic edge keys as well as nodes. Its weight callback accepts either immutable base weights or snapshot overlay weights. Keep `compute_route_on_graph` as the compatibility wrapper and rerun existing routing tests immediately.

Run: `cd backend; python -m pytest tests/test_routing.py -q`  
Expected: PASS before adding traffic behavior.

- [ ] **Step 6: Implement independent calculations and materiality labeling**

Calculate `base_path` first with base weights. Calculate `traffic_path` separately with the captured overlay. Generate at most one alternative whose directed edge set is disjoint from the selected primary route; return none when no such path exists. For matched non-closed edges use exactly:

```python
effective_time = base_travel_time * (
    observation.current_travel_time / observation.free_flow_travel_time
)
```

Do not clamp or substitute values. Determine materiality from selected-path changed weights or a validated closed edge on the base path that causes a different traffic path. Sum covered lengths on selected traversed edges and divide by selected route length.

- [ ] **Step 7: Run GREEN, full suite, and commit**

Run: `cd backend; python -m pytest tests/test_routing.py tests/test_traffic_routing.py -q`  
Run: `cd backend; python -m pytest -q`  
Run: `cd backend; python -m ruff check app tests`  
Commit: `git commit -m "feat: add immutable traffic-aware route calculation"`

---

### Task 6: Extend only the minimum API contracts

**Files:**
- Modify: `backend/app/schemas.py`
- Modify: `backend/app/map.py`
- Modify: `backend/app/main.py`
- Create: `backend/app/traffic/api.py`
- Modify: `backend/tests/test_map.py`
- Modify: `backend/tests/test_contracts.py`
- Create: `backend/tests/test_traffic_api.py`

**Interfaces:**
- Produces: `GET /api/v1/traffic/snapshot` read-only state.
- Extends: `POST /api/v1/routes/preview` response; request remains unchanged.
- Preserves: legacy `eta_seconds` as the selected route's effective ETA while adding unambiguous `base_eta` and `effective_eta`.

- [ ] **Step 1: Write failing base-fallback API tests**

With the TomTom key absent, route preview must return 200 and include:

```python
assert body["routing_source"] == "OSM_BASE_TRAVEL_TIME"
assert body["base_eta"] == body["effective_eta"] == body["eta_seconds"]
assert body["matched_traversed_edge_count"] == 0
assert body["traffic_coverage_ratio"] == 0
assert body["traffic_fallback_reason"] == "TOMTOM_API_KEY_MISSING"
```

The snapshot endpoint must expose state, retrieval/provider timestamps distinctly, freshness, fixed style/zoom, source reference, counts, and prototype-threshold metadata, while excluding observations' raw OpenLR and all secrets from the public response.

- [ ] **Step 2: Write failing traffic-adjusted and closure API tests**

Inject a frozen snapshot through the runtime boundary. Assert one weighted selected edge produces `TOMTOM_TRAFFIC_ADJUSTED` and length coverage. Assert a validated closure changing path selection produces the same label with zero traversed matched-edge count if no other selected edge is covered, while closure materiality is explicit.

- [ ] **Step 3: Run RED**

Run: `cd backend; python -m pytest tests/test_map.py tests/test_traffic_api.py -q`  
Expected: FAIL on missing fields/endpoint.

- [ ] **Step 4: Add schemas and wire the captured snapshot once**

`preview_route` loads one graph, calls `traffic_runtime.capture_snapshot(graph, ...)` once, and passes that exact object to `compute_traffic_aware_route`. It never reads the runtime again during the same calculation. Add a separate traffic router to `main.py`; do not add a refresh endpoint.

- [ ] **Step 5: Update Phase 01 anti-claim tests precisely**

Replace blanket assertions that prohibit the word `tomtom` with assertions that prohibit false `REAL_LIVE` or adjusted-routing claims in base fallback responses. Keep all Phase 01 planning and Golden Flow examples labeled `OSM_BASE_TRAVEL_TIME`; Phase 02 does not retrofit planning.

- [ ] **Step 6: Run GREEN, Golden Flow, full suite, and commit**

Run: `cd backend; python -m pytest tests/test_map.py tests/test_traffic_api.py tests/test_contracts.py tests/test_golden_flow.py -q`  
Run: `cd backend; python -m pytest -q`  
Run: `cd backend; python -m ruff check app tests`  
Commit: `git commit -m "feat: expose traffic-aware route provenance"`

---

### Task 7: Build and execute the fail-closed geospatial refresh

**Files:**
- Create: `backend/scripts/refresh_nasr_city_geospatial.py`
- Create: `backend/tests/test_geospatial_refresh.py`
- Modify: `backend/tests/test_geospatial_assets.py`
- Modify: `backend/tests/test_map.py`
- Replace after successful live validation: `data/processed/nasr_city/nasr_city_graph.graphml`
- Replace after successful live validation: `data/processed/nasr_city/nasr_city_emergency_facilities.geojson`
- Create after successful live validation: `data/processed/nasr_city/nasr_city_traffic_signals.geojson`
- Create after successful live validation: `data/processed/nasr_city/nasr_city_traffic_sample_points.geojson`
- Modify after successful live validation: `data/processed/nasr_city/provenance.json`

**Interfaces:**
- Produces: `validate_graph(graph)`, `validate_feature_collection(payload, name)`, `build_refresh_artifacts(boundary_path, staging_dir)`, and `publish_validated_artifacts(staging_dir, target_dir)`.
- The command runs only when explicitly invoked; importing it performs no network or filesystem mutation.

- [ ] **Step 1: Write failing validation and preservation tests**

Use tiny local graph/GeoJSON fixtures. Assert validation rejects undirected, empty, missing/invalid positive travel-time, missing one-way, and malformed feature collections. Snapshot all target file hashes, inject failure before publication, and assert every hash is unchanged.

- [ ] **Step 2: Write failing provenance and corridor-point tests**

Assert provenance records exact source semantics and computed artifact facts:

```python
artifact = provenance["artifacts"]["nasr_city_graph.graphml"]
assert artifact["source"] == "OpenStreetMap via OSMnx/Overpass"
assert artifact["source_reference"].startswith("https://")
assert "query=graph_from_polygon" in artifact["source_reference"]
assert datetime.fromisoformat(artifact["retrieved_at"]).tzinfo is not None
assert artifact["data_reality"] == "REAL_DERIVED"
assert artifact["freshness_status"] == "STATIC"
assert re.fullmatch(r"[0-9a-f]{64}", artifact["sha256"])
assert artifact["record_count"] > 0
```

Assert acquisition mode is `DIRECT_OSMNX_OVERPASS_OWNER_APPROVED`, Geofabrik is listed only as approved fallback/reproducibility, and turn restriction support is `NOT_PROCESSED_OR_VALIDATED`. Assert five sample features identify Rabaa, Tayaran, Abbas El Akkad, Makram Ebeid, and El Nasr Road and lie on validated named graph edges.

- [ ] **Step 3: Run RED**

Run: `cd backend; python -m pytest tests/test_geospatial_refresh.py -q`  
Expected: FAIL because the refresh script does not exist.

- [ ] **Step 4: Implement staged acquisition and validation**

Load the existing real boundary; call `ox.graph.graph_from_polygon(..., network_type="drive", simplify=True, retain_all=False)`, then `ox.routing.add_edge_speeds` and `ox.routing.add_edge_travel_times`. Request traffic signals and approved emergency facilities with bounded polygon queries. Never substitute fallback coordinates/features when queries fail.

Export to a sibling temporary directory. Validate every artifact and hash before publication. Publish through a checked target-directory swap with backup and rollback on exception; resolve all paths and refuse any target outside `data/processed/nasr_city`'s parent.

- [ ] **Step 5: Run GREEN without network**

Run: `cd backend; python -m pytest tests/test_geospatial_refresh.py -q`  
Run: `cd backend; python -m ruff check scripts tests/test_geospatial_refresh.py`  
Expected: PASS using faked acquisition functions.

- [ ] **Step 6: Install declared geospatial dependencies if the environment lacks them**

Run: `cd backend; python -m pip install -r requirements.txt`  
Review installed versions and licenses already declared by the repository. Do not add an unrelated dependency or hand-edit any lockfile.

- [ ] **Step 7: Execute one authorized live bounded refresh**

Run: `cd backend; python scripts/refresh_nasr_city_geospatial.py`  
If Overpass fails or validation fails, stop this task, report the provider evidence, and confirm the previous artifact hashes remain unchanged. Do not publish synthetic or partially validated data.

- [ ] **Step 8: Audit refreshed artifacts and run asset/map tests**

Run: `cd backend; python -m pytest tests/test_geospatial_refresh.py tests/test_geospatial_assets.py tests/test_map.py -q`  
Run a read-only audit that prints node/edge counts, one-way/access counts, corridor road names, artifact hashes, source labels, retrieval timestamp, and `NOT_PROCESSED_OR_VALIDATED` turn-restriction status. Do not print environment values.

- [ ] **Step 9: Run the full suite and commit code plus validated real artifacts**

Run: `cd backend; python -m pytest -q`  
Run: `cd backend; python -m ruff check app scripts tests`  
Run: `python -m compileall backend/app backend/scripts backend/tests`  
Commit: `git commit -m "data: refresh Nasr City OSM routing assets"`

---

### Task 8: Live TomTom smoke and final Phase 02 senior review

**Files:**
- Create: `docs/PHASE_02_REVIEW.md`
- Modify only if a verified defect is found: Phase 02 code/tests from Tasks 1–7.

**Interfaces:**
- Produces the required `PHASE 02 REVIEW` evidence and verdict.

- [ ] **Step 1: Reread all authoritative documents in the owner-specified order**

Read `AGENTS.md`, `docs/MASTER_PLAN.md`, `docs/DATA_LIST.md`, `docs/DECISIONS.md`, `docs/TECHNICAL_ARCHITECTURE_PLAN.md`, `docs/PHASE_00_FEASIBILITY_REPORT.md`, `docs/PHASE_01_REVIEW.md`, the approved Phase 02 design, and this plan.

- [ ] **Step 2: Inspect the complete Phase 02 diff**

Run: `git diff b2c1281..HEAD --stat` for historical context, then inspect the complete Phase 02 change with `git diff 0b2f1a6..HEAD`. Review tests before implementation along correctness, architecture, security, performance, and readability axes. Confirm no Phase 03 functionality or unrelated refactor entered the branch.

- [ ] **Step 3: Run one live TomTom smoke without leaking credentials**

Start one Uvicorn worker with the local environment loaded. Call one corridor route preview and `GET /api/v1/traffic/snapshot`. Record only sanitized status, snapshot ID, timestamps, freshness, style/zoom, observation/match counts, routing source, ETAs, and coverage. If the key is missing or TomTom fails, record visible base fallback; do not retry inside 60 seconds and do not claim live traffic.

- [ ] **Step 4: Repeat the live one-worker Golden Flow smoke**

Run the Phase 01 manual flow: health → list resources → create manual incident → generate plan → approve using returned `incident_version`. Confirm planning remains base-only and version/idempotency/concurrency behavior is unchanged.

- [ ] **Step 5: Run fresh final verification**

Run: `cd backend; python -m pytest -q`  
Run: `cd backend; python -m ruff check .`  
Run: `python -m compileall backend/app backend/scripts backend/tests`  
Run: `git diff --check`  
Read every command's complete output and record exact counts/status in the review.

- [ ] **Step 6: Perform explicit audits**

Audit real-vs-simulated labels, retrieval/provider timestamp separation, 60/120 boundaries, one 10-second deadline, fixed style/zoom, partial-result consistency, rate-limit/timeout fallback, route-label materiality, independent ETA semantics, length coverage, graph fingerprint binding, graph mutation absence, represented one-way/access handling, turn-restriction disclaimer, and secrets. Search for committed credential-like values and inspect tracked environment files without printing the real local `.env`.

- [ ] **Step 7: Write `docs/PHASE_02_REVIEW.md` in the required owner format**

Use these exact sections:

```markdown
# PHASE 02 REVIEW

Implemented:
Files changed:
Geospatial refresh:
Base graph:
TomTom runtime:
Traffic matching:
Traffic-aware routing:
Freshness/provenance:
Fallback behavior:
API contracts:
Tests:
Ruff:
Compile:
Live smoke:
Repo reconnaissance:
Real-vs-simulated audit:
Secrets audit:
Base-graph mutation audit:
Not implemented:
Decisions requested from owner:
Deviations:
Blocking issues:
Verdict: PASS | FIXES_REQUIRED
```

Replace the verdict marker with one evidence-backed verdict; do not leave both choices.

- [ ] **Step 8: Commit the reviewed Phase 02 result**

Run: `git status --short` and inspect the final staged diff.  
Commit: `git commit -m "docs: complete Phase 02 review"`  
Stop after `PASS` or `FIXES_REQUIRED`. Do not start Phase 03.

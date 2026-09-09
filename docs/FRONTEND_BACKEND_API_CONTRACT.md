# SirenGrid — Frontend ↔ Backend API Contract

Status: LOCKED FOR PHASE 03 IMPLEMENTATION
Backend baseline: integration/post-audit-reconcile
Backend SHA: 2d42d1467a67e960e0a8aaa08d42ee26fa967f6a
Frontend baseline: feature/frontend-design-implementation
Frontend SHA: 0a34ba2060909a20c017a0469e9561d8f4bf614d
Old integration donor: feature/phase-01-golden-flow
Donor SHA: 4314a8c0b976184d1bb7bf1393fb0a10f03bc640

---

## 1. Executive Summary & Baseline Lock

This contract document establishes the authoritative data and transport boundary between the canonical SirenGrid backend (`2d42d14`) and the approved frontend UI (`0a34ba2`).

All API specifications herein are derived strictly from the canonical backend code (`backend/app/main.py`, `backend/app/schemas.py`, routers, and behavioral test suite). The previous integration attempt (`4314a8c`) is treated purely as a donor reference; its invalid assumptions (e.g. `/social/*` routes, synthetic `/benchmark/phase08`, `{ "next": true }` simulation events, and `ResponsePlan` approval return types) are explicitly rejected and forbidden from porting.

---

## 2. Global Transport & Error Architecture

### 2.1 Network & Protocol Configuration
- **API Base Path:** `/api/v1`
- **Default Local Base URL:** `http://localhost:8000/api/v1`
- **Health Check:** `GET /api/v1/health`
  - Response: `{"status": "ok", "service": "SirenGrid API", "api_version": "v1"}`
- **Content-Type:** `application/json; charset=utf-8` (for all JSON payloads; multipart form-data is used exclusively for audio/image uploads in Phase 06 intake).
- **CORS Policy:** Allowed origins include `http://localhost:5173`, `http://127.0.0.1:5173`, `http://localhost:3000`, `http://127.0.0.1:3000`. Credentialed access (`allow_credentials=True`) is enforced; wildcard origins (`*`) are strictly forbidden by backend validator.
- **WebSocket Path:** `/api/v1/ws/operations` (e.g., `ws://localhost:8000/api/v1/ws/operations`).

### 2.2 Error Semantics & Response Envelopes
The canonical backend returns RFC 7807-compatible or standard FastAPI JSON error representations:
- **Validation Errors (422 Unprocessable Entity):**
  ```json
  {
    "detail": [
      {
        "loc": ["body", "expected_incident_version"],
        "msg": "field required",
        "type": "value_error.missing"
      }
    ]
  }
  ```
- **Entity Not Found (404 Not Found):**
  ```json
  {
    "detail": "Incident 'inc-123' not found"
  }
  ```
- **State & Concurrency Conflicts (409 Conflict):**
  Returned whenever an optimistic lock fails or a domain invariant is violated.
  Examples:
  - `{"detail": "STALE_INCIDENT_VERSION"}`
  - `{"detail": "STALE_PLAN_VERSION"}`
  - `{"detail": "PLAN_ALREADY_APPROVED"}`
  - `{"detail": "Cannot approve plan for incident with status CLOSED"}`
  - `{"detail": "Resource 'res-amb-01' is already assigned to active incident 'inc-999'"}`
- **Simulation Control Disabled (403 Forbidden):**
  ```json
  {
    "detail": "SIMULATION_DISABLED"
  }
  ```
  Occurs when any simulation mutation (`/simulation/reset`, `/simulation/load/*`, `/simulation/events`) is invoked while `settings.simulation_controls_enabled` is `False`.
- **Server Errors (500 Internal Server Error):**
  Standard internal server error envelope.
- **Frontend Recovery & Retry Policy:**
  - Read operations (`GET`): Safe to retry with exponential backoff.
  - Write operations (`POST`, `PATCH`): **NEVER** blindly retry a 409 conflict. The frontend must invalidate local state, refetch the latest entity state to acquire updated versions, display a conflict notification to the operator, and prompt for re-confirmation.

---

## 3. Canonical Endpoint Matrix

| Domain | Method | Path | Request Model | Response Model | Version Inputs | Important Errors | Reality / Provenance | Frontend Consumer | Target Phase |
|---|---|---|---|---|---|---|---|---|---|
| Health | `GET` | `/health` | None | `dict[str, str]` | None | None | Real System | App Shell / Liveness | Phase 03 |
| Incidents | `GET` | `/incidents` | None | `list[IncidentRead]` | None | 500 | Real / Sim / Syn | Incident Rail / Shell | Phase 03 |
| Incidents | `GET` | `/incidents/{incident_id}` | None | `IncidentRead` | None | 404 | Real / Sim / Syn | Incident Rail / Details | Phase 03 |
| Incidents | `POST` | `/intake/manual` | `ManualIncidentCreate` | `IncidentRead` | None | 422 | `REAL_PUBLIC` | Incident Intake | Phase 03 |
| Incidents | `PATCH` | `/incidents/{incident_id}/facts` | `IncidentFactsPatchRequest` | `IncidentFactsPatchResponse` | `expected_incident_version` | 404, 409, 422 | Tracked in Facts | Overview / Evidence | Phase 03 |
| Incidents | `POST` | `/incidents/{incident_id}/transition` | `IncidentTransitionRequest` | `IncidentRead` | `expected_incident_version` | 404, 409, 422 | Lifecycle Audit | Workflow progression | Phase 03 |
| Incidents | `POST` | `/incidents/{incident_id}/close` | `IncidentCloseRequest` | `IncidentRead` | `expected_incident_version` | 404, 409, 422 | Terminal Transition | Incident Actions | Phase 03 |
| Incidents | `POST` | `/incidents/{incident_id}/cancel` | `IncidentCancelRequest` | `IncidentRead` | `expected_incident_version` | 404, 409, 422 | Terminal Transition | Incident Actions | Phase 03 |
| Reports | `GET` | `/incidents/{incident_id}/reports` | None | `list[ReportRead]` | None | 404 | Real / Sim / Syn | Evidence Tab | Phase 03 |
| Reports | `POST` | `/incidents/{incident_id}/reports` | `ReportCreate` | `ReportRead` | None | 404, 422 | Attached to incident | Evidence Intake | Phase 03 |
| Reports | `GET` | `/reports/{report_id}` | None | `ReportRead` | None | 404 | Report Provenance | Evidence Detail | Phase 03 |
| Reports | `POST` | `/reports` | `ReportCreate` | `ReportRead` | None | 422 | Standalone intake | Dispatch Intake | Phase 03 |
| Timeline | `GET` | `/incidents/{incident_id}/timeline` | None | `list[TimelineEventRead]` | None | 404 | Event Sourced Audit | History Tab / Dock | Phase 03 |
| Planning | `GET` | `/incidents/{incident_id}/plans` | None | `list[ResponsePlanRead]` | None | 404 | Derived Planning | Plan Tab / Compare | Phase 03 |
| Planning | `POST` | `/incidents/{incident_id}/plans/generate-candidates` | None | `list[ResponsePlanRead]` | None | 404, 409 | Multi-Candidate Engine | Plan Tab ("Recalculate") | Phase 03 |
| Planning | `POST` | `/incidents/{incident_id}/plans/generate` | None | `ResponsePlanRead` | None | 404, 409 | Legacy / Single fallback | Plan Tab | Phase 03 |
| Planning | `GET` | `/plans/{plan_id}` | None | `ResponsePlanRead` | None | 404 | Plan Model | Plan Detail | Phase 03 |
| Planning | `POST` | `/plans/{plan_id}/select` | `SelectAlternativePlanRequest` | `ResponsePlanRead` | `expected_incident_version`, `expected_plan_version` | 404, 409, 422 | Selection Transition | Candidate Selection | Phase 03 |
| Planning | `POST` | `/plans/{plan_id}/approve` | `ApprovePlanRequest` | `ApprovalResult` | `expected_incident_version`, `expected_plan_version` | 404, 409, 422 | Commits Resources | Plan Tab ("Approve & Dispatch") | Phase 03 |
| Operations | `GET` | `/incidents/{incident_id}/operational-state` | None | `IncidentOperationalStateRead` | None | 404 | Unified State Snapshot | Operations Workspace | Phase 03 |
| Resources | `GET` | `/resources` | None (query: `resource_type`, `status`) | `list[ResourceRead]` | None | 500 | Public Emergency Units | Resources Screen / DenseMap | Phase 03 |
| Resources | `GET` | `/resources/{resource_id}` | None | `ResourceRead` | None | 404 | Resource Model | Resource Detail Drawer | Phase 03 |
| Resources | `PATCH` | `/resources/{resource_id}/state` | `ResourceStatePatchRequest` | `ResourceRead` | `expected_resource_version` | 404, 409, 422 | Resource State Machine | Resource Management | Phase 03 |
| Resources | `PATCH` | `/resources/{resource_id}/movement` | `ResourceMovementRequest` | `ResourceRead` | `expected_resource_version` | 404, 409, 422 | GPS Tracking | Telemetry Feed | Phase 03 |
| Resources | `POST` | `/resources/{resource_id}/assign` | `ResourceAssignRequest` | `ResourceRead` | `expected_resource_version` | 404, 409, 422 | Assignment Lock | Manual Dispatch | Phase 03 |
| Resources | `POST` | `/resources/{resource_id}/release` | `ResourceReleaseRequest` | `ResourceRead` | `expected_resource_version` | 404, 409, 422 | Release Lock | Handover / Clear | Phase 03 |
| Hospitals | `GET` | `/hospitals` | None | `list[HospitalRead]` | None | 500 | Static registry + Ops | Hospital Tab / Facilities | Phase 03 |
| Hospitals | `GET` | `/hospitals/{hospital_id}` | None | `HospitalRead` | None | 404 | Registry Record | Hospital Details | Phase 03 |
| Hospitals | `PATCH` | `/hospitals/{hospital_id}/simulation-state` | `HospitalOperationalStatePatchRequest` | `HospitalRead` | `expected_version` | 404, 409, 422 | Simulated capacity | Simulation Hooks | Phase 03 |
| Hospitals | `GET` | `/incidents/{incident_id}/hospital-options` | None | `HospitalOptionsResponse` | None | 404 | Ranked routing options | Hospital Tab | Phase 03 |
| Hospitals | `POST` | `/incidents/{incident_id}/hospital-options` | None | `HospitalOptionsResponse` | None | 404, 409 | Generates ranked set | Hospital Tab ("Refresh") | Phase 03 |
| Hospitals | `GET` | `/incidents/{incident_id}/hospital-destination` | None | `HospitalDestinationRead` | None | 404 | Selected destination | Hospital Tab | Phase 03 |
| Hospitals | `POST` | `/incidents/{incident_id}/hospital-destination/select` | `SelectHospitalDestinationRequest` | `HospitalDestinationRead` | `expected_incident_version`, `expected_plan_version`, `expected_option_set_version` | 404, 409, 422 | Commits destination | Hospital Tab ("Select") | Phase 03 |
| Hospitals | `GET` | `/incidents/{incident_id}/hospital-prealert` | None | `HospitalPreAlertRead` | None | 404 | Dispatch notification | Hospital Tab | Phase 03 |
| Hospitals | `POST` | `/incidents/{incident_id}/hospital-prealert` | `HospitalPreAlertRequest` | `HospitalPreAlertRead` | `expected_incident_version`, `expected_plan_version` | 404, 409, 422 | Gateway broadcast | Hospital Tab ("Send Pre-Alert") | Phase 03 |
| Corridor | `GET` | `/incidents/{incident_id}/corridor` | None | `CorridorRead` | None | 404 | Signal preemption | Overview Tab / Map | Phase 03 |
| Corridor | `POST` | `/incidents/{incident_id}/corridor` | `CorridorGenerateRequest` | `CorridorRead` | `expected_incident_version`, `expected_plan_version` | 404, 409, 422 | Computes Green Wave | Map / Route Actions | Phase 03 |
| Corridor | `POST` | `/incidents/{incident_id}/corridor/priority` | `CorridorPriorityRequest` | `CorridorRead` | `expected_corridor_version` | 404, 409, 422 | Signal gateway push | Signal Preemption Controls | Phase 03 |
| Driver Alert | `GET` | `/incidents/{incident_id}/resources/{resource_id}/driver-alert` | None | `DriverAlertRead` | None | 404 | In-vehicle guidance | Navigation View | Phase 03 |
| Driver Alert | `POST` | `/incidents/{incident_id}/resources/{resource_id}/driver-alert/refresh` | `DriverAlertRefreshRequest` | `DriverAlertRead` | `expected_resource_version` | 404, 409, 422 | Realtime path alert | Driver Alert Controls | Phase 03 |
| Traffic | `GET` | `/traffic/snapshot` | None | `TrafficSnapshotRead` | None | 500 | TomTom / OSM Derived | Traffic Status Bar | Phase 03 |
| Replanning | `GET` | `/incidents/{incident_id}/replan` | None | `ReplanEvaluationResponse` | None | 404 | Materiality Evaluation | Replan Banner / Dialog | Phase 03 |
| Replanning | `POST` | `/incidents/{incident_id}/replan/triggers` | `ReplanTriggerRequest` | `ReplanEvaluationRead` | None | 404, 422 | Ingests obstruction/delay | Simulation / Traffic Feed | Phase 03 |
| Replanning | `POST` | `/incidents/{incident_id}/replan/evaluate` | `ReplanEvaluateRequest` | `ReplanEvaluationResponse` | None | 404, 422 | Evaluates materiality | Dynamic Replanner | Phase 03 |
| Map Layers | `GET` | `/map/boundary` | None | `MapLayerResponse` | None | 500 | Nasr City GeoJSON | DenseMap Boundary | Phase 04 |
| Map Layers | `GET` | `/map/roads` | None | `MapLayerResponse` | None | 500 | Major network GeoJSON | DenseMap Road Network | Phase 04 |
| Map Layers | `GET` | `/map/zones` | None | `MapLayerResponse` | None | 500 | 500m Grid + Pop GeoJSON | DenseMap Coverage Layer | Phase 04 |
| Map Layers | `GET` | `/map/hospitals` | None | `MapLayerResponse` | None | 500 | Facilities GeoJSON | DenseMap Facility Pins | Phase 04 |
| Routes | `POST` | `/routes/preview` | `RoutePreviewRequest` | `RoutePreviewResponse` | None | 404, 422 | OSMnx / TomTom Graph | DenseMap Route Geometry | Phase 04 |
| Simulation | `GET` | `/simulation/status` | None | `SimulationStatusRead` | None | 500 | Controller Metadata | Demo Screen Controls | Phase 03 |
| Simulation | `POST` | `/simulation/reset` | None | `SimulationResetResponse` | None | 403 (if disabled) | Controller Reset | Demo Screen ("Reset") | Phase 03 |
| Simulation | `POST` | `/simulation/load/{scenario_id}` | None | `SimulationLoadResponse` | None | 403, 404 | Controller Scenario Load | Demo Screen ("Load Scenario") | Phase 03 |
| Simulation | `POST` | `/simulation/events` | `SimulationEventRequest` | `SimulationEventResponse` | Optional entity versions | 403, 404, 409, 422 | Applies bounded state change | Demo Screen ("Step/Inject") | Phase 03 |
| WebSocket | `WS` | `/ws/operations` | None (Client Inbound) | `OperationsEventEnvelope` | Monotonic stream `seq` | Connection drop | Live push stream | Operations Stream Provider | Phase 03 |

---

## 4. Incidents & Reports Specification

### 4.1 Incident Lifecycle & Transitions
Incidents follow strict directional state progression governed by `LOCKED_FORWARD_TRANSITIONS`:
- `RECEIVED` → `INTERPRETING`
- `INTERPRETING` → `ACTIVE_UNCONFIRMED`
- `ACTIVE_UNCONFIRMED` → `AWAITING_APPROVAL` (canonical: reached when candidate set is generated and persisted), `REQUIRES_REVIEW` (operator ambiguity hold)
- `AWAITING_APPROVAL` → `RESPONSE_ACTIVE` (canonical: reached when operator approves a response plan)
- `RESPONSE_ACTIVE` → `EN_ROUTE`
- `EN_ROUTE` → `ON_SCENE`
- `ON_SCENE` → `TRANSPORT_ACTIVE`, `HANDOVER`
- `TRANSPORT_ACTIVE` → `HANDOVER`
- `HANDOVER` → `CLOSED`
- `REQUIRES_REVIEW` → `ACTIVE_UNCONFIRMED` (released back to planning once operator updates facts)

**Terminal States:** `CLOSED`, `CANCELLED_FALSE_REPORT`, `DUPLICATE_MERGED`.
**Non-Actionable Guard:** `ensure_incident_actionable` raises 409 Conflict if candidate generation, planning, facts patching, or destination selection is attempted on an incident with status in `{CLOSED, CANCELLED_FALSE_REPORT, DUPLICATE_MERGED, REQUIRES_REVIEW}`.

### 4.2 Location Resolution & Sentinels
- If latitude and longitude are known, `location` is serialized as `{"lat": float, "lon": float}`.
- If unlocated, `location` is serialized as `null` (never a false 0.0 or string sentinel).
- Candidate planning requires valid coordinates; invoking `POST /plans/generate-candidates` on an unlocated incident returns 409 Conflict.

### 4.3 Provenance & Audit Fields
All incident and report records contain:
- `data_reality`: `REAL_PUBLIC` | `REAL_LIVE` | `REAL_DERIVED` | `SIMULATED` | `SYNTHETIC`
- `provenance_json`: Dictionary tracking source system, intake modality, ingestion timestamp, and confidence metadata.
- `version`: Monotonically increasing positive integer incremented on every transaction.

---

## 5. Candidate Generation & Plan Approval Contract

### 5.1 Plan States & Semantics
- `CANDIDATE`: Valid plan calculated by optimization engine, not currently selected.
- `RECOMMENDED`: The primary plan candidate currently recommended to the operator. Exactly one active candidate is `RECOMMENDED` at any time prior to approval.
- `APPROVED`: The plan confirmed and dispatched by human operator authority.
- `REJECTED` / `SUPERSEDED`: Inactive or historical plan.

> **CRITICAL SEMANTIC RULE:**
> `RECOMMENDED != APPROVED != DISPATCHED`.
> An AI-recommended plan MUST NOT assign resources or trigger green-wave preemption until explicit operator approval is committed.

### 5.2 The Plan Approval Endpoint & Schema
- **Endpoint:** `POST /api/v1/plans/{plan_id}/approve`
- **Request Body (`ApprovePlanRequest`):**
  ```json
  {
    "expected_incident_version": 2,
    "expected_plan_version": 1,
    "operator_reference": "dispatcher-op-01"
  }
  ```
- **Response Body (`ApprovalResult`):**
  ```json
  {
    "incident_status": "RESPONSE_ACTIVE",
    "incident": {
      "id": "inc-7c9b2f14-9a3c-4b6e-8210-95e2df894a11",
      "status": "RESPONSE_ACTIVE",
      "version": 3
    },
    "resources": [
      {
        "id": "res-amb-01",
        "version": 2,
        "name": "Ambulance Unit 01",
        "resource_type": "AMBULANCE",
        "status": "ASSIGNED",
        "operational_status": "ASSIGNED",
        "assigned_incident_id": "inc-7c9b2f14-9a3c-4b6e-8210-95e2df894a11",
        "assignment": "inc-7c9b2f14-9a3c-4b6e-8210-95e2df894a11"
      }
    ],
    "approval": {
      "id": "appr-12345",
      "plan_id": "plan-5f2b8492-4f38-4ce6-993d-83b6b19a771e",
      "incident_id": "inc-7c9b2f14-9a3c-4b6e-8210-95e2df894a11",
      "action": "APPROVE_PLAN",
      "operator_reference": "dispatcher-op-01",
      "expected_incident_version": 2,
      "expected_plan_version": 1,
      "created_at": "2026-09-06T18:06:00Z"
    }
  }
  ```
  *(Note: Does NOT return `ResponsePlanRead`. The frontend data layer must consume `ApprovalResult` and merge updated incident and resource states).*

---

## 6. Human Authority & Concurrency Conflict Matrix

| Operator Action | Canonical Endpoint | Request Payload | Required Version Checks | Success Response | 409 Conflict Meaning | Frontend Required Action | Supported Canonically? |
|---|---|---|---|---|---|---|---|
| Incident Progression | `POST /api/v1/incidents/{id}/transition` | `IncidentTransitionRequest` | `expected_incident_version` | `IncidentRead` (200) | Stale incident version or invalid forward transition | Prompt operator; refetch incident | YES |
| Cancel Incident | `POST /api/v1/incidents/{id}/cancel` | `IncidentCancelRequest` | `expected_incident_version` | `IncidentRead` (200) | Stale version or committed resources remain without force | Warn operator of active units; refresh | YES |
| Close Incident | `POST /api/v1/incidents/{id}/close` | `IncidentCloseRequest` | `expected_incident_version` | `IncidentRead` (200) | Stale version or active resources unreleased | Demand unit release prior to close | YES |
| Patch Incident Facts | `PATCH /api/v1/incidents/{id}/facts` | `IncidentFactsPatchRequest` | `expected_incident_version` | `IncidentFactsPatchResponse` (200) | Stale version or non-actionable status | Refetch incident facts; merge edits | YES |
| Generate Candidates | `POST /api/v1/incidents/{id}/plans/generate-candidates` | None | None | `list[ResponsePlanRead]` (200) | Incident unlocated or non-actionable | Alert operator of missing location | YES |
| Select Alternative Plan | `POST /api/v1/plans/{id}/select` | `SelectAlternativePlanRequest` | `expected_incident_version`, `expected_plan_version` | `ResponsePlanRead` (200) | Stale incident or plan version | Refetch plan candidates; update UI | YES |
| Approve Plan | `POST /api/v1/plans/{id}/approve` | `ApprovePlanRequest` | `expected_incident_version`, `expected_plan_version` | `ApprovalResult` (200) | Stale incident version, stale plan version, already approved, or resource contention | Notify operator; refetch plan and resources | YES |
| Reject Plan / Recalculate | N/A | N/A | N/A | N/A | N/A | Operator selects another candidate or clicks "Generate Candidates" | `BACKEND_CONTRACT_GAP` (Rejection verb not exposed; handled via alternative selection) |
| Generate Hospital Options | `POST /api/v1/incidents/{id}/hospital-options` | None | None | `HospitalOptionsResponse` (200) | Incident has no approved plan | Require plan approval first | YES |
| Select Hospital Destination | `POST /api/v1/incidents/{id}/hospital-destination/select` | `SelectHospitalDestinationRequest` | `expected_incident_version`, `expected_plan_version`, `expected_option_set_version` | `HospitalDestinationRead` (200) | Any of the 3 versions are stale, or hospital not in option set | Refetch hospital options; prompt reselection | YES |
| Hospital Pre-Alert | `POST /api/v1/incidents/{id}/hospital-prealert` | `HospitalPreAlertRequest` | `expected_incident_version`, `expected_plan_version` | `HospitalPreAlertRead` (200) | Destination not selected, stale versions, or already alerted | Refetch operational state; notify user | YES |
| Generate Corridor | `POST /api/v1/incidents/{id}/corridor` | `CorridorGenerateRequest` | `expected_incident_version`, `expected_plan_version` | `CorridorRead` (200) | Stale versions or route geometry missing | Refetch active plan routes | YES |
| Corridor Priority Update | `POST /api/v1/incidents/{id}/corridor/priority` | `CorridorPriorityRequest` | `expected_corridor_version` | `CorridorRead` (200) | Stale corridor version | Refetch corridor state | YES |
| Driver Alert Refresh | `POST /api/v1/incidents/{id}/resources/{id}/driver-alert/refresh` | `DriverAlertRefreshRequest` | `expected_resource_version` | `DriverAlertRead` (200) | Stale resource version or unassigned resource | Refetch resource status | YES |
| Approve Replacement Plan | `POST /api/v1/plans/{new_plan_id}/approve` | `ApprovePlanRequest` | `expected_incident_version`, `expected_plan_version` | `ApprovalResult` (200) | Stale incident version or replacement plan expired | Refetch replan evaluation | YES |
| Resource State Patch | `PATCH /api/v1/resources/{id}/state` | `ResourceStatePatchRequest` | `expected_resource_version` | `ResourceRead` (200) | Stale resource version or invalid state machine jump | Refetch resource list | YES |
| Simulation Events | `POST /api/v1/simulation/events` | `SimulationEventRequest` | Optional entity versions in payload | `SimulationEventResponse` (200) | Simulation disabled (403), entity not found (404), or version conflict (409) | Verify simulation enabled; refresh | YES |

---

## 7. Emergency Resources Specification

### 7.1 Canonical Resource Entity (`ResourceRead`)
- `id`: Unique identifier (e.g. `res-amb-01`)
- `name`: Display label (e.g. `Ambulance Unit 01`)
- `resource_type` / `type`: `AMBULANCE` | `FIRE_ENGINE` | `POLICE_INTERCEPTOR` | `RESCUE_BOAT`
- `status` / `operational_status`: `AVAILABLE` | `ASSIGNED` | `EN_ROUTE` | `ON_SCENE` | `TRANSPORTING` | `MAINTENANCE` | `OFF_DUTY`
- `latitude` & `longitude`: Float coordinates
- `location`: `{"lat": float, "lon": float}`
- `assigned_incident_id` / `assignment`: Active incident string ID or `null`
- `capabilities` / `capability_tags`: List of strings (e.g. `["BLS", "OXYGEN"]`, `["HEAVY_EXTRICATION"]`)
- `version`: Monotonically increasing resource version integer
- `last_updated`: ISO timestamp string
- `provenance`: `{"source": str, "data_reality": str}`
- `is_planner_eligible`: Boolean indicating if unit is unassigned, active, and available for assignment.

### 7.2 Data Boundary: Backend vs. Approved Frontend Mock
- **Present in Backend:** Real coordinates, operational status, incident binding, capability tags, optimistic lock versions, eligibility flags.
- **Only Present in Frontend Mocks (`mock.ts`):** Crew member names, vehicle odometer, remaining fuel percentage, battery level, tactical radio channel frequency, maintenance history notes.
- **Contract Rule:** Phase 03 will bind real operational fields from `ResourceRead`. Crew/maintenance mockup fields remain static presentation values and will not block runtime data integration.

---

## 8. Routing, Geospatial Layers & Map Boundary

### 8.1 Coordinates & Projection Standard
- Coordinate objects in requests/responses follow `{ "lat": float, "lon": float }`.
- GeoJSON geometries (`LineString`, `Polygon`, `Point`) in `/map/*` and route geometry follow RFC 7946 standard: `[longitude, latitude]` array pairs.
- Spatial reference: WGS84 (EPSG:4326).

### 8.2 Routing Behavior & Edge Cases
- **Route Preview Endpoint:** `POST /api/v1/routes/preview`
- **Zero-Distance / Same-Node Behavior:** If origin and destination snap to the identical graph node, the backend returns `distance_m = 0.0`, `eta_seconds = 0.0`, and single-point line coordinates without raising an error.
- **Unreachable / Outside Graph Error:** Returns 404 or 422 with `RouteNotFoundError` or `RoutingPointOutsideGraphError`.
- **Map Boundary Note:** Canonical route geometry provides vector paths and snap metadata. Real basemap tile rendering is scheduled for Phase 04. In Phase 03, the approved SVG map shell and facility markers are preserved without disruption.

---

## 9. Traffic Freshness & Dynamic Replanning

### 9.1 Traffic Snapshot (`GET /api/v1/traffic/snapshot`)
Returns:
- `overall_freshness`: `LIVE` | `FRESH` | `STALE` | `STATIC` | `UNKNOWN`
- `flow_reality`: `REAL_LIVE` | `REAL_PUBLIC` | `SIMULATED` | `SYNTHETIC`
- `sample_point_count`: Total monitored points
- `congested_point_count`: Points below speed thresholds
- `average_congestion_ratio`: 0.0 to 1.0 float
- **UNKNOWN Fallback Policy:** If traffic feed expires or fails, system downgrades to `STATIC` / `UNKNOWN` and falls back to baseline OSM edge speeds.

### 9.2 Replan State & Materiality
- **Inspection Endpoint:** `GET /api/v1/incidents/{incident_id}/replan`
- **Replan Evaluation Trigger:** Ingested via `POST /api/v1/incidents/{incident_id}/replan/triggers`.
- **Materiality Policy:** Replan is marked `material = true` only if ETA increases by > 60s or > 15%, active route edge overlap drops below 80%, a required resource becomes unavailable, or a route is blocked.
- **Replacement Workflow:**
  1. Material condition triggers replan evaluation.
  2. Engine calculates replacement candidate set and flags candidate as `RECOMMENDED`.
  3. Incident sets `pending_replan_plan_id`.
  4. Frontend displays Replan Banner with ETA delta and route comparison.
  5. Operator approves replacement plan via `POST /api/v1/plans/{replacement_plan_id}/approve`.
  6. Backend atomically supersedes old plan, assigns new units, updates `current_plan_id`, and clears `pending_replan_plan_id`.

---

## 10. Hospital Destination & Pre-Alert Contract

### 10.1 Hospital Entity & Options
- `HospitalRead`: Combines static registry (name, lat, lon, capacity, static capabilities) and simulated operational state (`accepting_state`, `simulated_load_ratio`, `simulated_free_capacity`, `incoming_cases`).
- `HospitalAcceptingState`: `ACCEPTING` | `DIVERTING` | `SATURATED`.
- Option Generation (`POST /incidents/{id}/hospital-options`): Ranks facilities based on travel time, capability match, load ratio, and freshness. Returns `HospitalOptionsResponse` with `option_set_version`.

### 10.2 Destination Selection & Pre-Alert
- Destination selection commits hospital choice using 3-way version check: `expected_incident_version`, `expected_plan_version`, `expected_option_set_version`.
- Pre-alert broadcasts arrival notification to the receiving facility gateway via `POST /incidents/{id}/hospital-prealert`.
- **Medical Boundary Guard:** Hospital evaluation is strictly operational/logistical (burn beds, pediatric trauma capability, travel ETA). Diagnosis, triage medical decisions, and clinical recommendations are outside system scope.

---

## 11. WebSocket Operations Stream Specification

| Specification Item | Canonical Truth |
|---|---|
| **URL / Path** | `/api/v1/ws/operations` (e.g. `ws://localhost:8000/api/v1/ws/operations`) |
| **Connection Model** | Persistent WebSocket connection managed by `OperationsConnectionManager`. Reconnect with exponential backoff on drop. |
| **Envelope Structure** | `{"event": str, "incident_id": str \| null, "timestamp": str (ISO), "version": int (monotonic seq), "payload": dict}` |
| **Published Events** | `incident.created`, `incident.updated`, `plan.approved`, `replan.required`, `replan.generated`, `resource.updated`, `hospital.updated`, `route.updated`, `timeline.appended` |
| **Stream Sequence** | Monotonically increasing 1-based integer (`version`). Starts at 1 on backend process boot. Increments exactly once per published event. |
| **Delivery Semantics** | In-memory, process-local, non-durable broadcast. Handed off to event loop; slow/stalled sockets are pruned without blocking request transactions. |
| **Recovery Strategy** | WebSocket is an **invalidation and live-nudge channel only**. It is **not** a durable event store. On reconnection or sequence gap detection, client MUST perform REST reconciliation against `/operational-state` or domain entity endpoints. |

---

## 12. Simulation Controller Contract

### 12.1 Activation & Security Guard
Simulation controls are disabled by default (`settings.simulation_controls_enabled: bool = False`). All mutation endpoints return `403 Forbidden` (`{"detail": "SIMULATION_DISABLED"}`) unless explicitly enabled in configuration.

### 12.2 Scenario Loading Semantics (`POST /api/v1/simulation/load/{scenario_id}`)
- Loads benchmark scenario metadata into the process-local `SimulationControllerState` (`loaded_scenario_id`, `seed`, `event_index=0`).
- **CRITICAL DISTINCTION:** `load/{scenario_id}` **DOES NOT** create, mutate, or hydrate operational database records (incidents, plans, resources). Domain state hydration remains governed by database seed scripts (`seed.py`) or explicit scenario test harnesses.

### 12.3 Event Injection Contract (`POST /api/v1/simulation/events`)
Requires exact `SimulationEventRequest` model (`extra="forbid"`):
```json
{
  "event_type": "RESOURCE_STATE",
  "resource_payload": {
    "resource_id": "res-amb-01",
    "status": "EN_ROUTE",
    "expected_resource_version": 1,
    "incident_id": "inc-2418"
  }
}
```
or
```json
{
  "event_type": "HOSPITAL_STATE",
  "hospital_payload": {
    "hospital_id": "hosp-nasr-01",
    "accepting_state": "DIVERTING",
    "simulated_load_ratio": 0.95,
    "simulated_free_capacity": 2,
    "expected_version": 1
  }
}
```
*(Donor integration attempt sent `{"next": true}` which causes immediate 422 validation failure).*

---

## 13. Deferred Features & Out-of-Scope Endpoints

The following features and endpoints exist either in feature branches, tests, or discarded donor code, but have **no registered canonical backend contract**. They MUST NOT be integrated in Phase 03:

1. **Social Media Intelligence (`/social/*`):**
   - Routes: `GET /social/signals`, `POST /social/refresh`, `POST /social/signals/{id}/dismiss`, `POST /social/signals/{id}/possible-new`, `POST /social/signals/{id}/associate`.
   - Classification: `DEFERRED / NOT PART OF CANONICAL FRONTEND INTEGRATION`.
2. **Benchmark REST Endpoint (`/benchmark/phase08`):**
   - Canonical benchmark validation is a standalone CLI runner (`backend/app/benchmark_cli.py`), not a web API router.
   - Classification: `DEFERRED_SCREEN` / Presentation-only mockup for Golden Demo.
3. **TomTom Incident Details Live Adapter:**
   - Classification: `DEFERRED_BACKEND_FEATURE`.

---

## 14. Frontend Field Mapping Matrix

| Approved Screen | UI Field / Control | Approved Mock Source (`mock.ts`) | Canonical Backend Source | Adapter / Transformation Needed? | Missing Backend Field? | Target Phase |
|---|---|---|---|---|---|---|
| **App Shell** | Status Strip / Active Incidents | `INCIDENTS` count | `GET /incidents` (filter active) | Count active status items | None | Phase 03 |
| **App Shell** | Network / System Health | Hardcoded "Nominal" | `GET /health` | Map `status: "ok"` to green pill | None | Phase 03 |
| **Incident Rail** | Incident Card List | `INCIDENTS` | `GET /incidents` | Map `IncidentRead` to card properties | None | Phase 03 |
| **Incident Rail** | Severity Badge | `sev: 'critical' \| 'high' \| ...` | `IncidentRead.severity` | Map enum case | None | Phase 03 |
| **Incident Rail** | Confidence Meter | `conf: 94` | `IncidentRead.confidence_level` | Convert level (`HIGH` → 90%, etc.) or use facts | None | Phase 03 |
| **Incident Rail** | Incident Location Text | `loc: 'Al Tayaran...'` | `IncidentRead.location_text` | Direct string | None | Phase 03 |
| **Overview Tab** | Key Metrics (Units, Corridor, ETA) | Hardcoded strings | `IncidentOperationalStateRead` | Format ETA seconds, unit count | None | Phase 03 |
| **Overview Tab** | Zone Coverage Bars | `COVERAGE_ZONES` | `ResponsePlanRead.metrics` & `/map/zones` | In Phase 03 derive from plan metrics | Zone polygon detail (Phase 04) | Phase 03 / 04 |
| **Overview Tab** | Executed Milestones | `ACTIVE_EXECUTED` | `GET /incidents/{id}/timeline` | Filter `TimelineEventRead` | None | Phase 03 |
| **Plan Tab** | Candidate Comparison Table | `PLAN_COMPARE` | `GET /incidents/{id}/plans` | Extract ETA, coverage drop, reserve score | None | Phase 03 |
| **Plan Tab** | Selected Route Details | `PLANS` | `ResponsePlanRead.routes` | Format route travel time & distance | None | Phase 03 |
| **Plan Tab** | "Approve & Dispatch" Button | Static button click | `POST /plans/{id}/approve` | Send versioned approval request | None | Phase 03 |
| **Hospital Tab** | Ranked Hospital List | `HOSPITALS` | `HospitalOptionsResponse.options` | Format ETA, capability match, load ratio | None | Phase 03 |
| **Hospital Tab** | "Select Hospital" Action | Static state toggle | `POST /hospital-destination/select` | Send 3-way versioned request | None | Phase 03 |
| **Hospital Tab** | "Send Pre-Alert" Action | Static state toggle | `POST /hospital-prealert` | Send pre-alert request | None | Phase 03 |
| **Evidence Tab** | Audio / Image / Text Items | `EVIDENCE_ITEMS` | `GET /incidents/{id}/reports` | Map `ReportRead.evidence_items_json` | None | Phase 03 |
| **Evidence Tab** | Arabic Transcript | `EVIDENCE_TRANSCRIPT_AR` | `ReportRead.raw_text` | Direct string | None | Phase 03 |
| **History Tab** | Timeline Event Stream | `HISTORY_EVENTS` | `GET /incidents/{id}/timeline` | Map `TimelineEventRead` | None | Phase 03 |
| **Resources Screen** | Resource Fleet Table | `MOCK_RESOURCES` | `GET /resources` | Map `ResourceRead` fields | Crew roster, fuel (keep mock) | Phase 03 |
| **Benchmark Screen** | KPI Graphs & Test Scenarios | `BENCHMARK_SCENARIOS` | N/A (CLI only) | Retain approved mock data | Web endpoint absent | Phase 03 (Keep Mock) |
| **Demo Screen** | Scenario Selector / Controls | Static demo controls | `GET /simulation/status`, `/load`, `/events` | Wire to simulation API | None | Phase 03 |
| **DenseMap** | Base Network & Facilities | SVG vectors & `FACILITIES` | `/map/boundary`, `/map/roads`, `/hospitals` | Render Leaflet / MapLibre layers | None | Phase 04 |

---

## 15. Mock Data Classification

| Mock Data Symbol (`mock.ts`) | Current Role | Classification | Phase Action |
|---|---|---|---|
| `INCIDENTS` | Initial incident list | `OPERATIONAL_REPLACE_PHASE03` | Replace with live `/incidents` state |
| `FOCUS_INCIDENT` | Default selected incident facts | `OPERATIONAL_REPLACE_PHASE03` | Replace with live `/incidents/{id}` |
| `PLANS` & `PLAN_COMPARE` | Response plan candidates & metrics | `OPERATIONAL_REPLACE_PHASE03` | Replace with live `/plans` candidate set |
| `HOSPITALS` | Hospital option list & capacities | `OPERATIONAL_REPLACE_PHASE03` | Replace with live hospital options |
| `EVIDENCE_ITEMS` & `TRANSCRIPT` | Multimodal dispatch evidence | `OPERATIONAL_REPLACE_PHASE03` | Replace with live reports & evidence |
| `HISTORY_EVENTS` | Timeline events | `OPERATIONAL_REPLACE_PHASE03` | Replace with live `/timeline` events |
| `MOCK_RESOURCES` (Fleet Status) | Resource operational status & location | `OPERATIONAL_REPLACE_PHASE03` | Replace operational fields with `/resources` |
| `MOCK_RESOURCES` (Crew/Fuel/Channel) | Vehicle maintenance & crew metadata | `PRESENTATION_ONLY_KEEP` | Preserve static display values in drawer |
| `COVERAGE_ZONES` | Zone percentage coverage comparison | `OPERATIONAL_REPLACE_PHASE03` | Compute from plan score breakdown |
| `FACILITIES`, `MARKERS`, `MAP_PATHS` | Static SVG map background & pins | `MAP_PRESENTATION_KEEP_UNTIL_PHASE04` | Preserve approved visual shell until Phase 04 |
| `BENCHMARK_SCENARIOS` & KPIs | Benchmark performance tab | `DEFERRED_SCREEN` | Retain approved presentation mocks |
| `STATE_META` & `DEC_TABS` | Navigation & tab layout metadata | `DESIGN_CONFIGURATION_KEEP` | Preserve layout configuration |

---

## 16. Donor Reuse Matrix

| Donor File / Function | What It Attempted | Canonical Compatibility | Visual Safety | Reuse in Phase 03? | Required Modifications |
|---|---|---|---|---|---|
| `api/client.ts` | Base fetch wrapper, error class, type guards | Compatible with adjustments | Safe (non-visual) | **REUSE WITH MODIFICATIONS** | Add robust 409 error details; support credentials and base URL config. |
| `api/operations.ts:listIncidents` | Fetch `/incidents` | 100% Compatible | Safe | **REUSE** | None. |
| `api/operations.ts:approvePlan` | Call `POST /plans/{id}/approve` | **Incompatible return type** | Safe | **REUSE WITH REWRITE** | Fix return model to `ApprovalResult`; consume `incident` and `resources`. |
| `api/operations.ts:selectHospitalDestination` | Call `/hospital-destination/select` | Compatible parameters | Safe | **REUSE** | Ensure 3-way version payload matches backend schema. |
| `api/operations.ts:triggerSimulationEvent` | Call `/simulation/events` | **Broken payload (`{next: true}`)** | Safe | **REUSE WITH REWRITE** | Adopt strict `SimulationEventRequest` model. |
| `api/operations.ts:listSocialSignals` | Call `/social/*` routes | **Non-existent routes** | Safe | **DO NOT PORT** | Exclude completely; social is deferred. |
| `api/operations.ts:getBenchmark` | Call `/benchmark/phase08` | **Non-existent route** | Safe | **DO NOT PORT** | Exclude completely; keep benchmark mock. |
| `state/OperationsContext.tsx` | Global React context for operations | Partially compatible | Safe | **REUSE AS REFERENCE ONLY** | Rewrite cleanly: remove social/benchmark state, handle monotonic WS sequences, and implement 409 conflict handling. |

---

## 17. Strict Do-Not-Port Register

The following donor artifacts are **strictly forbidden** from being copied into the codebase:
1. **Unsupported `/social/*` API calls:** Any code calling `/social/signals`, `/social/refresh`, `/social/signals/{id}/dismiss`, `/social/signals/{id}/possible-new`, or `/social/signals/{id}/associate`.
2. **Unsupported `/benchmark/phase08` API call:** Any code calling the non-existent benchmark endpoint.
3. **Invalid simulation payload `{"next": true}`:** Any call to `/simulation/events` that does not supply a valid `SimulationEventRequest`.
4. **Incorrect `approvePlan` return expectation:** Any code expecting `ResponsePlanRead` from `approvePlan` instead of `ApprovalResult`.
5. **Generic 409 error suppression:** Any handler that swallows 409 conflicts without reading `detail` or without prompting the operator.
6. **Frontend UI simplification or deletion:** Any attempt to delete, simplify, compress, or redesign approved screens, tabs, or styling.
7. **Premature MapLibre / Leaflet injection:** Any map engine replacement prior to Phase 04.

---

## 18. Phase 03 Allowed Implementation Surface

Phase 03 implementation is strictly confined to data-layer plumbing and controlled mock replacement.

### Permitted Implementation Files in Phase 03:
- `frontend/src/api/client.ts` (API transport and error wrapper)
- `frontend/src/api/types.ts` (TypeScript interfaces mirroring canonical Pydantic schemas)
- `frontend/src/api/operations.ts` (Domain API client functions)
- `frontend/src/state/OperationsContext.tsx` (State boundary and WebSocket invalidation manager)
- `frontend/.env.example` (API base URL configuration)
- `frontend/tests/*` (Focused data layer tests)

### Explicitly Forbidden in Phase 03:
- Visual redesigns or layout restructuring of `frontend/src/ops/*.tsx`.
- Modifying backend code (`backend/**`).
- Injecting real mapping libraries (`maplibre-gl`, `leaflet`).
- Removing presentation-only fleet details or benchmark mockups.

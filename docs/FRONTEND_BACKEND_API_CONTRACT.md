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
Canonical backend errors use standard FastAPI HTTP error envelopes with `detail`:
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
- **Service Unavailable (503 Service Unavailable):**
  ```json
  {
    "detail": "Corridor asset/route unavailable: ..."
  }
  ```
  Occurs when an upstream geospatial or routing asset required for operational calculation (e.g. corridor signal extraction) is missing or unreachable.
- **Server Errors (500 Internal Server Error):**
  Standard internal server error envelope.
- **Frontend Recovery & Retry Policy:**
  - Read operations (`GET`): Safe to retry with exponential backoff.
  - Write operations (`POST`, `PATCH`): **NEVER** blindly retry a 409 conflict. The frontend must invalidate local state, refetch the latest entity state to acquire updated versions, display a conflict notification to the operator, and prompt for re-confirmation.

---

## 3. Canonical Endpoint Matrix

| Domain | Method | Path | Request Model | Response Model | Version Inputs | Important Errors | Reality / Provenance | Frontend Consumer | Target Phase |
|---|---|---|---|---|---|---|---|---|---|
| Health | `GET` | `/health` | None | `dict[str, str]` | None | None | Real System | App Shell / Liveness | Phase 03 (Read) |
| Incidents | `GET` | `/incidents` | None | `list[IncidentRead]` | None | 500 | Real / Sim / Syn | Incident Rail / Shell | Phase 03 (Read) |
| Incidents | `GET` | `/incidents/{incident_id}` | None | `IncidentRead` | None | 404 | Real / Sim / Syn | Incident Rail / Details | Phase 03 (Read) |
| Incidents | `POST` | `/intake/manual` | `ManualIncidentCreate` | `IncidentRead` | None | 422 | `REAL_PUBLIC` | Incident Intake | Phase 03 (Client) / Phase 06 (UI Command) |
| Incidents | `PATCH` | `/incidents/{incident_id}/facts` | `IncidentFactsPatchRequest` | `IncidentFactsPatchResponse` | `expected_incident_version` | 404, 409, 422 | Tracked in Facts | Overview / Evidence | Phase 03 (Client) / Phase 06 (UI Command) |
| Incidents | `POST` | `/incidents/{incident_id}/transition` | `IncidentTransitionRequest` | `IncidentRead` | `expected_incident_version` | 404, 409, 422 | Lifecycle Audit | Workflow progression | Phase 03 (Client) / Phase 06 (UI Command) |
| Incidents | `POST` | `/incidents/{incident_id}/close` | `IncidentCloseRequest` | `IncidentRead` | `expected_incident_version` | 404, 409, 422 | Terminal Transition | Incident Actions | Phase 03 (Client) / Phase 06 (UI Command) |
| Incidents | `POST` | `/incidents/{incident_id}/cancel` | `IncidentCancelRequest` | `IncidentRead` | `expected_incident_version` | 404, 409, 422 | Terminal Transition | Incident Actions | Phase 03 (Client) / Phase 06 (UI Command) |
| Reports | `GET` | `/incidents/{incident_id}/reports` | None | `list[ReportRead]` | None | 404 | Real / Sim / Syn | Evidence Tab | Phase 03 (Read) |
| Reports | `POST` | `/incidents/{incident_id}/reports` | `ReportCreate` | `ReportRead` | None | 404, 422 | Attached to incident | Evidence Intake | Phase 03 (Client) / Phase 06 (UI Command) |
| Reports | `GET` | `/reports/{report_id}` | None | `ReportRead` | None | 404 | Report Provenance | Evidence Detail | Phase 03 (Read) |
| Reports | `POST` | `/reports` | `ReportCreate` | `ReportRead` | None | 422 | Standalone intake | Dispatch Intake | Phase 03 (Client) / Phase 06 (UI Command) |
| Timeline | `GET` | `/incidents/{incident_id}/timeline` | None | `list[TimelineEventRead]` | None | 404 | Event Sourced Audit | History Tab / Dock | Phase 03 (Read) |
| Planning | `GET` | `/incidents/{incident_id}/plans` | None | `list[ResponsePlanRead]` | None | 404 | Derived Planning | Plan Tab / Compare | Phase 03 (Read) |
| Planning | `POST` | `/incidents/{incident_id}/plans/generate-candidates` | None | `list[ResponsePlanRead]` | None | 404, 409 | Multi-Candidate Engine | Plan Tab ("Recalculate") | Phase 03 (Client) / Phase 06 (UI Command) |
| Planning | `POST` | `/incidents/{incident_id}/plans/generate` | None | `ResponsePlanRead` | None | 404, 409 | Legacy / Single fallback | Plan Tab | Phase 03 (Client) / Phase 06 (UI Command) |
| Planning | `GET` | `/plans/{plan_id}` | None | `ResponsePlanRead` | None | 404 | Plan Model | Plan Detail | Phase 03 (Read) |
| Planning | `POST` | `/plans/{plan_id}/select` | `SelectAlternativePlanRequest` | `ResponsePlanRead` | `expected_incident_version`, `expected_plan_version` | 404, 409, 422 | Selection Transition | Candidate Selection | Phase 03 (Client) / Phase 06 (UI Command) |
| Planning | `POST` | `/plans/{plan_id}/approve` | `ApprovePlanRequest` | `ApprovalResult` | `expected_incident_version`, `expected_plan_version` | 404, 409, 422 | Commits Resources | Plan Tab ("Approve & Dispatch") | Phase 03 (Client) / Phase 06 (UI Command) |
| Operations | `GET` | `/incidents/{incident_id}/operational-state` | None | `IncidentOperationalStateRead` | None | 404 | Unified State Snapshot | Operations Workspace | Phase 03 (Read) |
| Resources | `GET` | `/resources` | None (query: `resource_type`, `status`) | `list[ResourceRead]` | None | 500 | Public Emergency Units | Resources Screen / DenseMap | Phase 03 (Read) |
| Resources | `GET` | `/resources/{resource_id}` | None | `ResourceRead` | None | 404 | Resource Model | Resource Detail Drawer | Phase 03 (Read) |
| Resources | `PATCH` | `/resources/{resource_id}/state` | `ResourceStatePatchRequest` | `ResourceRead` | `expected_resource_version` | 404, 409, 422 | Resource State Machine | Resource Management | Phase 03 (Client) / Phase 06 (UI Command) |
| Resources | `PATCH` | `/resources/{resource_id}/movement` | `ResourceMovementRequest` | `ResourceRead` | `expected_resource_version` | 404, 409, 422 | GPS Tracking | Telemetry Feed | Phase 03 (Client) / Phase 06 (UI Command) |
| Resources | `POST` | `/resources/{resource_id}/assign` | `ResourceAssignRequest` | `ResourceRead` | `expected_resource_version` | 404, 409, 422 | Assignment Lock | Manual Dispatch | Phase 03 (Client) / Phase 06 (UI Command) |
| Resources | `POST` | `/resources/{resource_id}/release` | `ResourceReleaseRequest` | `ResourceRead` | `expected_resource_version` | 404, 409, 422 | Release Lock | Handover / Clear | Phase 03 (Client) / Phase 06 (UI Command) |
| Hospitals | `GET` | `/hospitals` | None | `list[HospitalRead]` | None | 500 | Static registry + Ops | Hospital Tab / Facilities | Phase 03 (Read) |
| Hospitals | `GET` | `/hospitals/{hospital_id}` | None | `HospitalRead` | None | 404 | Registry Record | Hospital Details | Phase 03 (Read) |
| Hospitals | `PATCH` | `/hospitals/{hospital_id}/simulation-state` | `HospitalOperationalStatePatchRequest` | `HospitalRead` | `expected_version` | 404, 409, 422 | Simulated capacity | Simulation Hooks | Phase 03 (Client) / Phase 06 (UI Command) |
| Hospitals | `GET` | `/incidents/{incident_id}/hospital-options` | None | `HospitalOptionsResponse` | None | 404 | Ranked routing options | Hospital Tab | Phase 03 (Read) |
| Hospitals | `POST` | `/incidents/{incident_id}/hospital-options` | None | `HospitalOptionsResponse` | None | 404, 409 | Generates ranked set | Hospital Tab ("Refresh") | Phase 03 (Client) / Phase 06 (UI Command) |
| Hospitals | `GET` | `/incidents/{incident_id}/hospital-destination` | None | `HospitalDestinationRead` | None | 404 | Selected destination | Hospital Tab | Phase 03 (Read) |
| Hospitals | `POST` | `/incidents/{incident_id}/hospital-destination/select` | `SelectHospitalDestinationRequest` | `HospitalDestinationRead` | `expected_incident_version`, `expected_plan_version`, `expected_option_set_version` | 404, 409, 422 | Commits destination | Hospital Tab ("Select") | Phase 03 (Client) / Phase 06 (UI Command) |
| Hospitals | `GET` | `/incidents/{incident_id}/hospital-prealert` | None | `HospitalPreAlertRead` | None | 404 | Dispatch notification | Hospital Tab | Phase 03 (Read) |
| Hospitals | `POST` | `/incidents/{incident_id}/hospital-prealert` | `HospitalPreAlertRequest` | `HospitalPreAlertRead` | `expected_incident_version`, `expected_plan_version` | 404, 409, 422 | Gateway broadcast | Hospital Tab ("Send Pre-Alert") | Phase 03 (Client) / Phase 06 (UI Command) |
| Corridor | `GET` | `/incidents/{incident_id}/corridor` | None | `CorridorRead` | None | 404 | Signal preemption | Overview Tab / Map | Phase 03 (Read) |
| Corridor | `POST` | `/incidents/{incident_id}/corridor` | `CorridorGenerateRequest` | `CorridorRead` | None | 404, 409, 422, 503 | Computes Green Wave | Map / Route Actions | Phase 03 (Client) / Phase 06 (UI Command) |
| Corridor | `POST` | `/incidents/{incident_id}/corridor/priority` | `CorridorPriorityRequest` | `CorridorRead` | `expected_incident_version`, `expected_plan_version` | 404, 409, 422 | Signal gateway push | Signal Preemption Controls | Phase 03 (Client) / Phase 06 (UI Command) |
| Driver Alert | `GET` | `/incidents/{incident_id}/resources/{resource_id}/driver-alert` | None | `DriverAlertRead` | None | 404 | In-vehicle guidance | Navigation View | Phase 03 (Read) |
| Driver Alert | `POST` | `/incidents/{incident_id}/resources/{resource_id}/driver-alert/refresh` | `DriverAlertRefreshRequest` | `DriverAlertRead` | `expected_resource_version` | 404, 409, 422 | Realtime path alert | Driver Alert Controls | Phase 03 (Client) / Phase 06 (UI Command) |
| Traffic | `GET` | `/traffic/snapshot` | None | `TrafficSnapshotRead` | None | 500 | TomTom / OSM Derived | Traffic Status Bar | Phase 03 (Read) |
| Replanning | `GET` | `/incidents/{incident_id}/replan` | None | `ReplanEvaluationRead \| None` | None | 404 | Materiality Evaluation | Replan Banner / Dialog | Phase 03 (Read) |
| Replanning | `POST` | `/incidents/{incident_id}/replan/triggers` | `ReplanTriggerRequest` | `ReplanEvaluationRead` | `expected_incident_version` | 404, 409, 422 | Ingests obstruction/delay | Simulation / Traffic Feed | Phase 03 (Client) / Phase 06 (UI Command) |
| Replanning | `POST` | `/incidents/{incident_id}/replan/evaluate` | `ReplanEvaluateRequest` | `ReplanEvaluationResponse` | `expected_incident_version` | 404, 409, 422 | Evaluates materiality | Dynamic Replanner | Phase 03 (Client) / Phase 06 (UI Command) |
| Map Layers | `GET` | `/map/boundary` | None | `MapLayerResponse` | None | 500 | Nasr City GeoJSON | DenseMap Boundary | Phase 04 |
| Map Layers | `GET` | `/map/roads` | None | `MapLayerResponse` | None | 500 | Major network GeoJSON | DenseMap Road Network | Phase 04 |
| Map Layers | `GET` | `/map/zones` | None | `MapLayerResponse` | None | 500 | 500m Grid + Pop GeoJSON | DenseMap Coverage Layer | Phase 04 |
| Map Layers | `GET` | `/map/hospitals` | None | `MapLayerResponse` | None | 500 | Facilities GeoJSON | DenseMap Facility Pins | Phase 04 |
| Routes | `POST` | `/routes/preview` | `RoutePreviewRequest` | `RoutePreviewResponse` | None | 404, 422 | OSMnx / TomTom Graph | DenseMap Route Geometry | Phase 04 |
| Simulation | `GET` | `/simulation/status` | None | `SimulationStatusRead` | None | 500 | Controller Metadata | Demo Screen Controls | Phase 03 (Read) |
| Simulation | `POST` | `/simulation/reset` | None | `SimulationResetResponse` | None | 403 (if disabled) | Controller Reset | Demo Screen ("Reset") | Phase 03 (Client) / Phase 06 (UI Command) |
| Simulation | `POST` | `/simulation/load/{scenario_id}` | None | `SimulationLoadResponse` | None | 403, 404 | Controller Scenario Load | Demo Screen ("Load Scenario") | Phase 03 (Client) / Phase 06 (UI Command) |
| Simulation | `POST` | `/simulation/events` | `SimulationEventRequest` | `SimulationEventResponse` | Optional entity versions | 403, 404, 409, 422 | Applies bounded state change | Demo Screen ("Step/Inject") | Phase 03 (Client) / Phase 06 (UI Command) |
| WebSocket | `WS` | `/ws/operations` | None (Client Inbound) | `OperationsEventEnvelope` | Monotonic stream `seq` | Connection drop | Live push stream | Operations Stream Provider | Phase 05 |

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
- `data_reality`: Canonical `DataReality` enum (`REAL_PUBLIC` | `REAL_LIVE` | `REAL_DERIVED` | `SIMULATED` | `SYNTHETIC`).
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
  `ApprovalResult` directly subclasses and extends `ResponsePlanRead`. It inherits all plan fields (`id`, `plan_id`, `incident_id`, `incident_version`, `plan_version`, `status`, `resource_ids`, `routes`, `metrics`, `score_breakdown`, `created_at`) and additionally provides authoritative operational state updates:
  ```json
  {
    "id": "plan-5f2b8492-4f38-4ce6-993d-83b6b19a771e",
    "plan_id": "plan-5f2b8492-4f38-4ce6-993d-83b6b19a771e",
    "incident_id": "inc-7c9b2f14-9a3c-4b6e-8210-95e2df894a11",
    "incident_version": 3,
    "plan_version": 1,
    "version": 1,
    "status": "APPROVED",
    "resource_ids": ["res-amb-01"],
    "routes": [
      {
        "resource_id": "res-amb-01",
        "distance_m": 1250.5,
        "eta_seconds": 187.5,
        "routing_source": "OSM_BASE_TRAVEL_TIME"
      }
    ],
    "metrics": {
      "max_arrival_eta_seconds": 187.5,
      "mean_arrival_eta_seconds": 187.5,
      "selected_resource_count": 1,
      "routing_source": "OSM_BASE_TRAVEL_TIME"
    },
    "score_breakdown": {
      "algorithm": "MIN_BASE_ROUTE_ETA_WITH_HARD_AVAILABILITY_CONSTRAINTS",
      "traffic_source": "OSM_BASE_TRAVEL_TIME"
    },
    "created_at": "2026-09-06T18:05:00Z",
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
  The frontend data layer must consume `ApprovalResult` and apply its authoritative incident and resource state updates directly rather than assuming the response is merely a bare plan.

---

## 6. Human Authority & Concurrency Conflict Matrix

| Operator Action | Canonical Endpoint | Request Payload | Required Version Checks | Success Response | 409 / 503 Behavior | Frontend Required Action | UI Command Ownership |
|---|---|---|---|---|---|---|---|
| Incident Progression | `POST /api/v1/incidents/{id}/transition` | `IncidentTransitionRequest` | `expected_incident_version` | `IncidentRead` (200) | 409: Stale incident version or invalid forward transition | Prompt operator; refetch incident | Phase 06 |
| Cancel Incident | `POST /api/v1/incidents/{id}/cancel` | `IncidentCancelRequest` | `expected_incident_version` | `IncidentRead` (200) | 409: Stale incident version, or an approved plan is active / responders are committed (cancellation is only safe before operational response commitment; responders are never silently demobilized; controlled operational resolution required) | Inform operator that committed responders prevent false-report cancellation; require unit clearance | Phase 06 |
| Close Incident | `POST /api/v1/incidents/{id}/close` | `IncidentCloseRequest` | `expected_incident_version` | `IncidentRead` (200) | 409: Stale version or active resources unreleased | Demand unit release prior to close | Phase 06 |
| Patch Incident Facts | `PATCH /api/v1/incidents/{id}/facts` | `IncidentFactsPatchRequest` | `expected_incident_version` | `IncidentFactsPatchResponse` (200) | 409: Stale version or non-actionable status | Refetch incident facts; merge edits | Phase 06 |
| Generate Candidates | `POST /api/v1/incidents/{id}/plans/generate-candidates` | None | None | `list[ResponsePlanRead]` (200) | 409: Incident unlocated or non-actionable | Alert operator of missing location | Phase 06 |
| Select Alternative Plan | `POST /api/v1/plans/{id}/select` | `SelectAlternativePlanRequest` | `expected_incident_version`, `expected_plan_version` | `ResponsePlanRead` (200) | 409: Stale incident or plan version | Refetch plan candidates; update UI | Phase 06 |
| Approve Plan | `POST /api/v1/plans/{id}/approve` | `ApprovePlanRequest` | `expected_incident_version`, `expected_plan_version` | `ApprovalResult` (200) | 409: Stale incident version, stale plan version, already approved, or resource contention | Notify operator; refetch plan and resources | Phase 06 |
| Reject Plan / Recalculate | N/A | N/A | N/A | N/A | N/A | Operator selects another candidate or clicks "Generate Candidates" | `BACKEND_CONTRACT_GAP` (Rejection verb not exposed; handled via alternative selection) |
| Generate Hospital Options | `POST /api/v1/incidents/{id}/hospital-options` | None | None | `HospitalOptionsResponse` (200) | 409: Incident has no approved plan | Require plan approval first | Phase 06 |
| Select Hospital Destination | `POST /api/v1/incidents/{id}/hospital-destination/select` | `SelectHospitalDestinationRequest` | `expected_incident_version`, `expected_plan_version`, `expected_option_set_version` | `HospitalDestinationRead` (200) | 409: Any of the 3 versions are stale, or hospital not in option set | Refetch hospital options; prompt reselection | Phase 06 |
| Hospital Pre-Alert | `POST /api/v1/incidents/{id}/hospital-prealert` | `HospitalPreAlertRequest` | `expected_incident_version`, `expected_plan_version` | `HospitalPreAlertRead` (200) | 409: Destination not selected, stale versions, or already alerted | Refetch operational state; notify user | Phase 06 |
| Generate Corridor | `POST /api/v1/incidents/{id}/corridor` | `CorridorGenerateRequest` | None | `CorridorRead` (200) | 409: Incident has no approved plan or resource not in active plan. 503: Corridor assets or routing graph data unavailable | Refetch active plan routes; render degraded/unavailable status on 503 | Phase 06 |
| Corridor Priority Update | `POST /api/v1/incidents/{id}/corridor/priority` | `CorridorPriorityRequest` | `expected_incident_version`, `expected_plan_version` | `CorridorRead` (200) | 409: Stale incident or plan version | Refetch corridor state | Phase 06 |
| Driver Alert Refresh | `POST /api/v1/incidents/{id}/resources/{id}/driver-alert/refresh` | `DriverAlertRefreshRequest` | `expected_resource_version` | `DriverAlertRead` (200) | 409: Stale resource version or unassigned resource | Refetch resource status | Phase 06 |
| Ingest Replan Trigger | `POST /api/v1/incidents/{id}/replan/triggers` | `ReplanTriggerRequest` | `expected_incident_version` | `ReplanEvaluationRead` (200) | 409: Stale incident version or unknown trigger reasons | Refetch incident; retry trigger | Phase 06 |
| Evaluate Replan | `POST /api/v1/incidents/{id}/replan/evaluate` | `ReplanEvaluateRequest` | `expected_incident_version` | `ReplanEvaluationResponse` (200) | 409: Stale incident version or no active plan | Refetch incident and replan state | Phase 06 |
| Approve Replacement Plan | `POST /api/v1/plans/{new_plan_id}/approve` | `ApprovePlanRequest` | `expected_incident_version`, `expected_plan_version` | `ApprovalResult` (200) | 409: Stale incident version or replacement plan expired | Refetch replan evaluation | Phase 06 |
| Resource State Patch | `PATCH /api/v1/resources/{id}/state` | `ResourceStatePatchRequest` | `expected_resource_version` | `ResourceRead` (200) | 409: Stale resource version or invalid state machine jump | Refetch resource list | Phase 06 |
| Simulation Events | `POST /api/v1/simulation/events` | `SimulationEventRequest` | Optional entity versions in payload | `SimulationEventResponse` (200) | 403: Simulation disabled. 404: Entity not found. 409: Version conflict | Verify simulation enabled; refresh | Phase 06 |

---

## 7. Emergency Resources Specification

### 7.1 Canonical Resource Entity (`ResourceRead`)
- `id`: Unique identifier (e.g. `res-amb-01`)
- `name`: Display label (e.g. `Ambulance Unit 01`)
- `resource_type` / `type`: Canonical `ResourceType` enum (`AMBULANCE` | `FIRE_RESCUE`)
- `status` / `operational_status`: Canonical `ResourceStatus` enum (`AVAILABLE` | `RESERVED` | `ASSIGNED` | `EN_ROUTE` | `ON_SCENE` | `TRANSPORTING` | `OUT_OF_SERVICE`)
- `latitude` & `longitude`: Float coordinates
- `location`: `{"lat": float, "lon": float}`
- `assigned_incident_id` / `assignment`: Active incident string ID or `null`
- `capabilities` / `capability_tags`: List of strings (e.g. `["BLS", "OXYGEN"]`, `["HEAVY_EXTRICATION"]`)
- `version`: Monotonically increasing resource version integer
- `last_updated`: ISO timestamp string
- `provenance`: `{"source": str, "data_reality": str}`
- `is_planner_eligible`: Boolean indicating if unit is unassigned, active, and available for assignment.

### 7.2 Presentation-Only Telemetry Truth Boundary
- **Present in Backend:** Real coordinates, operational status, incident binding, capability tags, optimistic lock versions, eligibility flags.
- **Only Present in Frontend Mocks (`mock.ts`):** Crew member names, vehicle odometer, remaining fuel percentage, battery level, tactical radio channel frequency, vehicle service records.
- **Contract Rule & Truth Boundary:** Any retained mock fields (crew member names, fuel percentage, battery level, radio channel frequency, service notes) must be visually marked as demo/presentation-only, strictly isolated from operational decisions, never presented as live/real backend truth, and never used to compute availability, eligibility, ETA, or planning. If labeling them clearly would confuse the operator screen, Phase 03 should prefer hiding or neutralizing the field rather than displaying fabricated operational telemetry.

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
Returns `TrafficSnapshotRead` matching canonical backend fields and exact nullability:
- `snapshot_id`: `str | None`
- `version`: `int | None`
- `provider_state`: `str | None` (e.g. `LIVE_FLOW_ACTIVE`, `FALLBACK_BASELINE`)
- `refresh_attempted_at`: `datetime (ISO) | None`
- `retrieved_at`: `datetime (ISO) | None`
- `provider_last_updated`: `datetime (ISO) | None`
- `freshness_status`: `FreshnessStatus` (`LIVE` | `FRESH` | `STALE` | `STATIC` | `UNKNOWN`)
- `source`: `str`
- `source_reference`: `str | None`
- `data_reality`: `DataReality | None` (complete enum: `REAL_PUBLIC` | `REAL_LIVE` | `REAL_DERIVED` | `SIMULATED` | `SYNTHETIC`)
- `flow_style`: `str` (`absolute`)
- `flow_zoom`: `int` (`22`)
- `units`: `str` (`kmph`)
- `observation_count`: `int`
- `match_count`: `int`
- `matched_edge_count`: `int`
- `failure_reason`: `str | None`
- `prototype_policy`: `TrafficPrototypePolicyRead` containing:
  - `refresh_interval_seconds`: `60`
  - `fresh_max_age_seconds`: `120`
  - `refresh_timeout_seconds`: `10`
  - `min_provider_confidence`: `0.8`
  - `max_geometry_separation_m`: `30`
  - `max_direction_difference_degrees`: `30`
- **UNKNOWN Fallback Policy:** If the traffic provider fails or feed expires, the backend marks `freshness_status = "UNKNOWN"` or `"STATIC"`, leaves provider timestamps/metadata as `null`, and falls back to baseline OSM edge speeds. The frontend must not invent aggregate congestion ratios or sample point counts not provided by the model.

### 9.2 Replan State & Materiality Authority
- **Inspection Endpoint:** `GET /api/v1/incidents/{incident_id}/replan` (returns `ReplanEvaluationRead | None`).
- **Replan Evaluation Trigger:** Ingested via `POST /api/v1/incidents/{incident_id}/replan/triggers` requiring `expected_incident_version: int`, `trigger_reasons: list[str]`, and `input_references: dict[str, Any]`.
- **Replan Evaluation Command:** Triggered via `POST /api/v1/incidents/{incident_id}/replan/evaluate` requiring `expected_incident_version: int`.
- **Materiality Policy Authority:** The **backend is strictly authoritative for `material`**. The frontend must **NEVER recompute or reproduce the materiality algorithm** in the browser. The backend engine evaluates a complex multi-factor policy across travel time changes, active route geometry/edge overlap, road closures, unreachability, resource contention or unavailability, operator requirement changes, hospital diversion, and joint coverage drops. The frontend's role is strictly to display the backend-evaluated `material`, `status`, `trigger_reasons`, `explanation`, and candidate replacement plans.
- **Replacement Workflow:**
  1. Material condition triggers replan evaluation.
  2. Engine calculates replacement candidate set and flags candidate as `RECOMMENDED`.
  3. Incident sets `pending_replan_plan_id`.
  4. Frontend displays Replan Banner with ETA delta and route comparison.
  5. Operator approves replacement plan via `POST /api/v1/plans/{replacement_plan_id}/approve` with `expected_incident_version` and `expected_plan_version`.
  6. Backend atomically supersedes old plan, assigns new units, updates `current_plan_id`, and clears `pending_replan_plan_id`.

---

## 10. Hospital Destination & Pre-Alert Contract

### 10.1 Hospital Entity & Options
- `HospitalRead`: Combines static registry (name, lat, lon, capacity, static capabilities) and simulated operational state (`accepting_state`, `simulated_load_ratio`, `simulated_free_capacity`, `incoming_cases`).
- `HospitalAcceptingState`: Canonical enum (`ACCEPTING` | `NOT_ACCEPTING` | `UNKNOWN`).
- Option Generation (`POST /incidents/{id}/hospital-options`): Ranks facilities based on travel time, capability match, load ratio, and freshness. Returns `HospitalOptionsResponse` with `option_set_version`.

### 10.2 Destination Selection & Pre-Alert
- Destination selection commits hospital choice using 3-way version check: `expected_incident_version`, `expected_plan_version`, `expected_option_set_version`.
- Pre-alert broadcasts arrival notification to the receiving facility gateway via `POST /incidents/{id}/hospital-prealert` with `expected_incident_version` and `expected_plan_version`.
- **Medical Boundary Guard:** Hospital evaluation is strictly operational/logistical (burn beds, pediatric trauma capability, travel ETA). Diagnosis, triage medical decisions, and clinical recommendations are outside system scope.

---

## 11. WebSocket Operations Stream Specification

| Specification Item | Canonical Truth |
|---|---|
| **URL / Path** | `/api/v1/ws/operations` (e.g. `ws://localhost:8000/api/v1/ws/operations`) |
| **Connection Model** | Persistent WebSocket connection managed on the backend by `OperationsConnectionManager`. In the frontend, reconnection with exponential backoff on drop is a client-side requirement implemented in Phase 05. |
| **Envelope Structure** | `{"event": str, "incident_id": str \| null, "timestamp": str (ISO), "version": int (monotonic seq), "payload": dict}` |
| **Published Events** | `incident.created`, `incident.updated`, `plan.approved`, `replan.required`, `replan.generated`, `resource.updated`, `hospital.updated`, `route.updated`, `timeline.appended` |
| **Stream Sequence** | Monotonically increasing 1-based integer (`version`). Starts at 1 on backend process boot. Increments exactly once per published event. |
| **Delivery Semantics** | In-memory, process-local, non-durable broadcast. Handed off to event loop; slow/stalled sockets are pruned without blocking request transactions. |
| **Recovery Strategy** | WebSocket is an **invalidation and live-nudge channel only**. It is **not** a durable event store. On reconnection or sequence gap detection, client MUST perform REST reconciliation against `/operational-state` or domain entity endpoints. |
| **Implementation Phase** | **Phase 05 (REST + WebSocket Integration)**. Documented in Phase 02 for transport alignment; Phase 03 MUST NOT implement WebSocket runtime behavior. |

---

## 12. Simulation Controller Contract

### 12.1 Activation & Security Guard
Simulation controls are disabled by default (`settings.simulation_controls_enabled: bool = False`). All mutation endpoints return `403 Forbidden` (`{"detail": "SIMULATION_DISABLED"}`) unless explicitly enabled in configuration.

### 12.2 Scenario Loading Semantics (`POST /api/v1/simulation/load/{scenario_id}`)
- Loads benchmark scenario metadata into the process-local `SimulationControllerState` (`loaded_scenario_id`, `seed`, `event_index=0`).
- **CRITICAL DISTINCTION:** `load/{scenario_id}` **DOES NOT** create, mutate, or hydrate operational database records (incidents, plans, resources). Domain state hydration remains governed by database seed scripts (`seed.py`) or explicit scenario test harnesses. The frontend must not imply that loading a scenario creates active domain state.

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
    "accepting_state": "NOT_ACCEPTING",
    "simulated_load_ratio": 0.95,
    "simulated_free_capacity": 2,
    "expected_version": 1
  }
}
```
*(Donor integration attempt sent `{"next": true}` which causes immediate 422 validation failure. Hospital accepting state must be one of `ACCEPTING`, `NOT_ACCEPTING`, or `UNKNOWN`).*

---

## 13. Deferred Features & Out-of-Scope Endpoints

The following features and endpoints exist either in feature branches, tests, or discarded donor code, but have **no registered canonical backend contract**. They MUST NOT be integrated in Phase 03:

1. **Social Media Intelligence (`/social/*`):**
   - Routes: `GET /social/signals`, `POST /social/refresh`, `POST /social/signals/{id}/dismiss`, `POST /social/signals/{id}/possible-new`, `POST /social/signals/{id}/associate`.
   - Classification: `DEFERRED / NOT PART OF CANONICAL FRONTEND INTEGRATION`.
2. **Benchmark REST Endpoint (`/benchmark/phase08`):**
   - Canonical benchmark validation is a standalone CLI runner (`backend/app/benchmark_cli.py`), not a web API router.
   - Classification: `DEFERRED_SCREEN` / Synthetic benchmark fixture for Golden Demo.
3. **TomTom Incident Details Live Adapter:**
   - Classification: `DEFERRED_BACKEND_FEATURE`.

---

## 14. Frontend Field Mapping Matrix

| Approved Screen | UI Field / Control | Approved Mock Source (`mock.ts`) | Canonical Backend Source | Adapter / Transformation Needed? | Missing Backend Field? | Target Phase |
|---|---|---|---|---|---|---|
| **App Shell** | Status Strip / Active Incidents | `INCIDENTS` count | `GET /incidents` (filter active) | Count active status items | None | Phase 03 (Read) |
| **App Shell** | Network / System Health | Hardcoded "Nominal" | `GET /health` | Map `status: "ok"` to green pill | None | Phase 03 (Read) |
| **Incident Rail** | Incident Card List | `INCIDENTS` | `GET /incidents` | Map `IncidentRead` to card properties | None | Phase 03 (Read) |
| **Incident Rail** | Severity Badge | `sev: 'critical' \| 'high' \| ...` | `IncidentRead.severity` | Map enum case | None | Phase 03 (Read) |
| **Incident Rail** | Confidence Meter | `conf: 94` | `IncidentRead.confidence_level` | Render truthful categorical badge (`HIGH`, `MEDIUM`, `LOW`); NEVER fabricate numeric % | None | Phase 03 (Read) |
| **Incident Rail** | Incident Location Text | `loc: 'Al Tayaran...'` | `IncidentRead.location_text` | Direct string | None | Phase 03 (Read) |
| **Overview Tab** | Key Metrics (Units, Corridor, ETA) | Hardcoded strings | `IncidentOperationalStateRead` | Format ETA seconds, unit count | None | Phase 03 (Read) |
| **Overview Tab** | Zone Coverage Bars | `COVERAGE_ZONES` | `ResponsePlanRead.metrics` & `/map/zones` | Display precomputed backend metric or retain presentation-only mode; NEVER compute coverage % in client | Polygon rendering deferred to Phase 04 | Phase 03 / 04 |
| **Overview Tab** | Executed Milestones | `ACTIVE_EXECUTED` | `GET /incidents/{id}/timeline` | Filter `TimelineEventRead` | None | Phase 03 (Read) |
| **Plan Tab** | Candidate Comparison Table | `PLAN_COMPARE` | `GET /incidents/{id}/plans` | Extract ETA, coverage drop, reserve score | None | Phase 03 (Read) |
| **Plan Tab** | Selected Route Details | `PLANS` | `ResponsePlanRead.routes` | Format route travel time & distance | None | Phase 03 (Read) |
| **Plan Tab** | "Approve & Dispatch" Button | Static button click | `POST /plans/{id}/approve` | Send versioned approval request | None | Phase 03 (Client) / Phase 06 (UI Command) |
| **Hospital Tab** | Ranked Hospital List | `HOSPITALS` | `HospitalOptionsResponse.options` | Format ETA, capability match, load ratio | None | Phase 03 (Read) |
| **Hospital Tab** | "Select Hospital" Action | Static state toggle | `POST /hospital-destination/select` | Send 3-way versioned request | None | Phase 03 (Client) / Phase 06 (UI Command) |
| **Hospital Tab** | "Send Pre-Alert" Action | Static state toggle | `POST /hospital-prealert` | Send pre-alert request | None | Phase 03 (Client) / Phase 06 (UI Command) |
| **Evidence Tab** | Audio / Image / Text Items | `EVIDENCE_ITEMS` | `GET /incidents/{id}/reports` | Map `ReportRead.evidence_items_json` | None | Phase 03 (Read) |
| **Evidence Tab** | Arabic Transcript | `EVIDENCE_TRANSCRIPT_AR` | `ReportRead.raw_text` | Direct string | None | Phase 03 (Read) |
| **History Tab** | Timeline Event Stream | `HISTORY_EVENTS` | `GET /incidents/{id}/timeline` | Map `TimelineEventRead` | None | Phase 03 (Read) |
| **Resources Screen** | Resource Fleet Table | `MOCK_RESOURCES` | `GET /resources` | Map `ResourceRead` fields | Crew roster, fuel (mark presentation-only) | Phase 03 (Read) |
| **Benchmark Screen** | KPI Graphs & Test Scenarios | `BENCHMARK_SCENARIOS` | N/A (CLI only) | Explicitly label as synthetic evaluation fixture; not live measurement | Web endpoint absent | Phase 03 (Mock Fixture) |
| **Demo Screen** | Scenario Selector / Controls | Static demo controls | `GET /simulation/status`, `/load`, `/events` | Wire to simulation API | None | Phase 03 (Client) / Phase 06 (UI Command) |
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
| `MOCK_RESOURCES` (Crew/Fuel/Channel) | Vehicle service records & crew metadata | `PRESENTATION_ONLY_KEEP` | Mark demo-only; isolate from operational decisions; never treat as live |
| `COVERAGE_ZONES` | Zone percentage coverage comparison | `OPERATIONAL_REPLACE_PHASE03` | Display precomputed backend metrics or keep presentation mode; frontend does not calculate coverage |
| `FACILITIES`, `MARKERS`, `MAP_PATHS` | Static SVG map background & pins | `MAP_PRESENTATION_KEEP_UNTIL_PHASE04` | Preserve approved visual shell until Phase 04 |
| `BENCHMARK_SCENARIOS` & KPIs | Benchmark performance tab | `DEFERRED_SCREEN` | Labeled explicitly as synthetic benchmark fixture / demo evidence; non-operational |
| `STATE_META` & `DEC_TABS` | Navigation & tab layout metadata | `DESIGN_CONFIGURATION_KEEP` | Preserve layout configuration |

---

## 16. Donor Reuse Matrix

| Donor File / Function | What It Attempted | Canonical Compatibility | Visual Safety | Reuse in Phase 03? | Required Modifications |
|---|---|---|---|---|---|
| `api/client.ts` | Base fetch wrapper, error class, type guards | Compatible with adjustments | Safe (non-visual) | **REUSE WITH MODIFICATIONS** | Add robust 409 error details; support credentials and base URL config. |
| `api/operations.ts:listIncidents` | Fetch `/incidents` | 100% Compatible | Safe | **REUSE** | None. |
| `api/operations.ts:approvePlan` | Call `POST /plans/{id}/approve` | **Incompatible return type** | Safe | **REUSE WITH REWRITE** | Fix return model to `ApprovalResult`; consume `incident` and `resources`. Client foundation in Phase 03; UI command wiring in Phase 06. |
| `api/operations.ts:selectHospitalDestination` | Call `/hospital-destination/select` | Compatible parameters | Safe | **REUSE** | Ensure 3-way version payload matches backend schema. Client foundation in Phase 03; UI command wiring in Phase 06. |
| `api/operations.ts:triggerSimulationEvent` | Call `/simulation/events` | **Broken payload (`{next: true}`)** | Safe | **REUSE WITH REWRITE** | Adopt strict `SimulationEventRequest` model with `RESOURCE_STATE` or `HOSPITAL_STATE`. |
| `api/operations.ts:listSocialSignals` | Call `/social/*` routes | **Non-existent routes** | Safe | **DO NOT PORT** | Exclude completely; social is deferred. |
| `api/operations.ts:getBenchmark` | Call `/benchmark/phase08` | **Non-existent route** | Safe | **DO NOT PORT** | Exclude completely; keep benchmark mock. |
| `state/OperationsContext.tsx` | Global React context for operations | Partially compatible | Safe | **REUSE AS REFERENCE ONLY** | Rewrite cleanly: remove social/benchmark state; Phase 03 wires REST read state only; WebSocket is deferred to Phase 05. |

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
8. **Premature WebSocket integration:** Any attempt to connect or consume WebSockets during Phase 03 (deferred to Phase 05).
9. **Premature Operator Authority UI wiring:** Any attempt to wire live operator-authority commands (plan approval, destination selection, transitions) before Phase 06.

---

## 18. Phase 03 Allowed Implementation Surface & Typing Principles

Phase 03 implementation is strictly confined to data-layer plumbing and controlled mock replacement.

### 18.1 Phase 03 vs. Phase 05 Architecture Boundary
- **Phase 03 (Data Layer & Controlled Mock Replacement):**
  - Transport / client foundation (`request`, `ApiError`).
  - Strict TypeScript schema interfaces mirroring canonical backend schemas.
  - Read-oriented domain API wrappers (`listIncidents`, `getIncident`, `listReports`, `listPlans`, `getOperationalState`, `listResources`, `listHospitals`, `getTrafficSnapshot`).
  - Minimal state boundary providing read data and replacing approved operational mocks.
  - No WebSocket runtime behavior.
  - No human-authority mutation UX wiring.
- **Phase 05 (REST + WebSocket Integration):**
  - Production WebSocket connection lifecycle, reconnect with exponential backoff, and event stream subscription.
  - Monotonic stream sequence tracking and gap detection.
  - Process-local push invalidation and targeted/full REST reconciliation upon disconnect or sequence gap.

### 18.2 Phase 03 vs. Phase 06 Authority Command Ownership
- **Phase 03 Scope:** May define typed mutation request models and minimal API client helper functions for mutations (`approvePlan`, `selectHospitalDestination`, etc.).
- **Phase 06 Scope (Human Authority + Version Guards + Conflict Handling):** Owns all UI button wiring, operator confirmation modals, optimistic version checks, 409 conflict handling, retry prompts, and transactional UI state transitions.

### 18.3 TypeScript Phase 03 Null & Unknown Handling Principle
TypeScript interfaces created in Phase 03 must preserve backend nullability and unknown/degraded states exactly. The frontend must not replace `null` with fabricated operational defaults:
- **Unresolved Incident Location:** Must be typed as `location: Coordinate | null`, and serialized/rendered as unresolved/null (never substituted with `(0, 0)` or sample coordinates).
- **Traffic Snapshot Nullability:** Fields such as `snapshot_id`, `version`, `provider_state`, `refresh_attempted_at`, `retrieved_at`, `provider_last_updated`, `source_reference`, `data_reality`, and `failure_reason` must be strictly typed as `T | null`. When unavailable, the UI displays degraded/unknown status without fabricating values.
- **Absent Replan:** Must be typed as `ReplanEvaluationRead | null`.
- **Absent Hospital Destination / Pre-Alert:** Must remain `null` until explicitly selected / dispatched.
- **Categorical Enums:** `ConfidenceLevel` (`HIGH`, `MEDIUM`, `LOW`), `HospitalAcceptingState` (`ACCEPTING`, `NOT_ACCEPTING`, `UNKNOWN`), and `FreshnessStatus` (`LIVE`, `FRESH`, `STALE`, `STATIC`, `UNKNOWN`) must be preserved as discrete string enums. The client must never map categorical levels to fabricated numeric percentages.

### 18.4 Permitted Implementation Files in Phase 03:
- `frontend/src/api/client.ts` (API transport and error wrapper)
- `frontend/src/api/types.ts` (TypeScript interfaces mirroring canonical Pydantic schemas)
- `frontend/src/api/operations.ts` (Domain REST API client functions)
- `frontend/src/state/OperationsContext.tsx` (State boundary and REST-capable data provider for Phase 03; WebSocket integration is deferred to Phase 05)
- `frontend/.env.example` (API base URL configuration)
- `frontend/tests/*` (Focused data layer tests)

### 18.5 Explicitly Forbidden in Phase 03:
- Implementing WebSocket connection, message handling, or live invalidation (deferred to Phase 05).
- Wiring live human-authority mutation commands in UI buttons/screens (deferred to Phase 06).
- Visual redesigns or layout restructuring of `frontend/src/ops/*.tsx`.
- Modifying backend code (`backend/**`).
- Injecting real mapping libraries (`maplibre-gl`, `leaflet`).
- Removing presentation-only fleet details or benchmark mockups.
- Fabricating numeric confidence percentages or calculating operational coverage values in the client.

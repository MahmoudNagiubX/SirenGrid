# SirenGrid Phase 01 — Foundation, Contracts & Minimal Golden Flow Implementation Plan

> **Status:** READY AFTER PHASE 00 IS MERGED
>
> **Goal:** Build the first real integrated SirenGrid vertical slice:
>
> `manual operator intake → persisted incident → available simulated resources → real OSM route evaluation → minimal candidate response plan → version-checked human approval → resource assignment → active route/state → frontend-consumable REST payload`
>
> **Architecture:** Python 3.12 FastAPI modular monolith, one backend instance/worker, Pydantic v2, SQLAlchemy 2.x + SQLite WAL, OSMnx/NetworkX routing, file-backed geospatial assets. The backend remains the only operational source of truth.
>
> **Spec:** `docs/TECHNICAL_ARCHITECTURE_PLAN.md` v1.1
>
> **Product Authority:** `docs/MASTER_PLAN.md` v1.2
>
> **Data Authority:** `docs/DATA_LIST.md`
>
> **Agent Rules:** `AGENTS.md`
>
> **Phase 00 Result:** PASS. Structured AI extraction has no selected provider; Phase 01 uses manual/operator structured intake. AI structured extraction remains disabled by default until later validation.
>
> **Important:** This plan supersedes the old pre-v1.1 Phase 01 plan.

---

# 0. What This Phase Means in Plain English

Phase 00 proved the tools/providers/environment were usable and identified that structured AI extraction was not yet safe enough.

Phase 01 now builds the first actual SirenGrid workflow.

The operator will manually enter a structured emergency. SirenGrid will persist it, look at simulated responder availability, use a real Nasr City OSM road graph to calculate responder ETA/routes, build a minimal real response plan, let the operator approve that exact version, assign the selected resources transactionally, and return the active route/state through stable API contracts.

This phase does **not** yet build the coverage optimizer, TomTom traffic matching, hospital scoring, AI extraction, WebSocket live movement, corridor, or replanning. Those extend this working vertical slice later.

---

# 1. Locked Decisions Used by This Phase

- Technical Architecture v1.1 is locked.
- Backend: Python 3.12 + FastAPI modular monolith.
- Runtime: one backend instance / one worker.
- Persistence: SQLAlchemy 2.x + SQLite WAL.
- Backend owns operational truth.
- Critical approval commands are version/state checked.
- Resource state is simulated for the MVP but drives real deterministic SirenGrid logic.
- Routing uses real OSM-derived Nasr City graph data.
- TomTom is not integrated in this phase.
- Frontend stack is still deferred; backend contracts must be frontend-agnostic.
- Structured AI extraction is disabled by default in Phase 01.
- Manual/operator structured intake is the safe Phase 01 intake path.
- Unknown incident facts remain unknown.
- No citizen-facing SirenGrid reporting flow.
- No hidden response doctrine may be invented by an LLM or developer.

---

# 2. Important Phase-01 Interpretation of Response Requirements

The architecture states that response requirements may come from explicit source information, operator confirmation, or a later approved prototype response-requirement matrix.

The prototype response-requirement matrix is **not implemented yet**.

Therefore, in Phase 01 the operator must explicitly supply the resource types/counts needed for the manual incident.

Example:

```json
{
  "required_resources": [
    {"resource_type": "AMBULANCE", "count": 1},
    {"resource_type": "FIRE_RESCUE", "count": 1}
  ]
}
```

This deliberately avoids inventing dispatch doctrine.

---

# 3. Hard Scope Boundary

## Must implement

1. FastAPI runtime foundation.
2. SQLite WAL + foreign keys.
3. Stable shared enums/contracts.
4. Initial SQLAlchemy models for Incident, EmergencyResource, ResponsePlan, Approval, minimal TimelineEvent.
5. Explicit simulated responder seed data.
6. Existing Nasr City donor geospatial asset import.
7. Real OSMnx/NetworkX base route calculation.
8. Manual/operator incident intake.
9. Resource listing.
10. Minimal deterministic candidate-plan generator.
11. Version-checked, transactional plan approval.
12. Active route/resource state after approval.
13. Health/map/API contracts.
14. Frontend/mock contract examples.
15. Automated Golden Flow integration test.

## Must NOT implement

- Groq/Gemini structured incident extraction,
- ASR product integration,
- image product integration,
- report fusion,
- TomTom traffic overlay,
- refreshed Geofabrik pipeline,
- turn-restriction claims unless explicitly validated,
- WorldPop coverage,
- resource repositioning,
- hospital ranking/pre-alert,
- corridor,
- driver alert,
- WebSocket operations stream,
- vehicle movement,
- dynamic replanning,
- scenario engine,
- benchmark runner,
- frontend implementation,
- Social Media Intelligence.

---

# 4. Mandatory Repository Reconnaissance

Before implementing non-trivial code, inspect these references and report what was actually reused.

## Primary direct donor

`MahmoudNagiubX/Egypt-Smart-City-Digital-Twin`

Pinned Phase-01 reference commit:

`93ca9e90e2fc52c914dd5ccbe42bdc84ce745d3d`

Inspect:

- `backend/app/main.py`
- `backend/app/config.py`
- `backend/app/weather_impact/routing.py`
- `backend/app/data/nasr_city/processed/nasr_city_boundary.geojson`
- `backend/app/data/nasr_city/processed/nasr_city_grid_500m.geojson`
- `backend/app/data/nasr_city/processed/nasr_city_graph.graphml`
- `backend/app/data/nasr_city/processed/nasr_city_emergency_facilities.geojson`

Useful routing patterns to understand/adapt:

- `load_routing_graph`
- `find_nearest_graph_node`
- `_haversine_distance_m`
- `snap_coordinate_to_graph`
- `compute_route`
- `get_route_edge_data`
- `sum_route_metric`
- route geometry conversion

Preserve the useful behavior that rejects coordinates unreasonably far from the service graph instead of silently snapping kilometres away.

Do not import weather-risk logic.

## Selective reference: ResQPath

`ashwinnm13/ResQPath`

Inspect:

- `backend/routers/incident.py`
- `backend/routers/dispatch.py`
- `backend/routers/route.py`
- `backend/routers/ambulance.py`
- `backend/models/`
- `backend/tests/`

Useful ideas:
- focused FastAPI router shapes,
- basic incident/resource endpoint flow,
- nearest-resource query concepts,
- end-to-end dispatch sequencing.

Explicitly reject these ResQPath behaviors:

1. assigning the nearest unit regardless of availability/status,
2. converting route failure into zero distance/zero duration,
3. automatically choosing hospital behavior in Phase 01,
4. patient/medical ML fields that SirenGrid does not require,
5. OpenRouteService dependency for SirenGrid base routing.

SirenGrid uses its own OSM graph and must fail visibly when a route cannot be computed.

## Required completion-report fields

```text
Repo reconnaissance performed:
Relevant references:
Files/patterns inspected:
What was reused:
What was rewritten/adapted:
Rejected donor behavior:
Why the result fits SirenGrid:
```

---

# 5. Preflight — Close Phase 00 Before Phase 01

Phase 01 must begin from a clean, reviewable baseline.

```powershell
git status
git branch --show-current
```

The completed Phase 00 work must be committed.

Suggested:

```powershell
git add .
git commit -m "research: complete phase 00 feasibility gates"
git push -u origin research/phase-00-feasibility
```

Merge Phase 00 through the repository's normal review process.

After Phase 00 is on `main`:

```powershell
git switch main
git pull --ff-only origin main
git switch -c feature/phase-01-golden-flow
```

Do not start Phase 01 from an uncommitted Phase 00 workspace.

---

# 6. Target Repository Shape After Phase 01

```text
backend/
├── app/
│   ├── __init__.py
│   ├── main.py
│   ├── config.py
│   ├── db.py
│   ├── schemas.py
│   ├── models.py
│   ├── incidents.py
│   ├── resources.py
│   ├── routing.py
│   ├── planning.py
│   └── seed.py
├── tests/
│   ├── conftest.py
│   ├── test_health.py
│   ├── test_db.py
│   ├── test_schemas.py
│   ├── test_incidents.py
│   ├── test_resources.py
│   ├── test_routing.py
│   ├── test_planning.py
│   ├── test_approval.py
│   ├── test_map.py
│   └── test_golden_flow.py
├── requirements.txt
└── .env.example

data/
├── processed/
│   └── nasr_city/
│       ├── nasr_city_boundary.geojson
│       ├── nasr_city_grid_500m.geojson
│       ├── nasr_city_graph.graphml
│       ├── nasr_city_emergency_facilities.geojson
│       └── provenance.json
└── scenarios/
    └── phase01_resources.json
```

If the repository already has an equivalent focused file, modify it instead of creating a duplicate abstraction.

---

# 7. Runtime Dependencies

`backend/requirements.txt` should include only Phase-01/runtime requirements:

```text
fastapi
uvicorn[standard]
pydantic>=2,<3
sqlalchemy>=2,<3
httpx
osmnx
networkx
shapely
pyproj
geopandas
pytest
ruff
```

Do not add LangChain, LlamaIndex, Redis, Celery, vector DBs, TomTom SDKs, or AI orchestration frameworks.

---

# 8. Shared Enums

Implement in `backend/app/schemas.py`:

```python
class DataReality(str, Enum):
    REAL_PUBLIC = "REAL_PUBLIC"
    REAL_LIVE = "REAL_LIVE"
    REAL_DERIVED = "REAL_DERIVED"
    SIMULATED = "SIMULATED"
    SYNTHETIC = "SYNTHETIC"

class FreshnessStatus(str, Enum):
    LIVE = "LIVE"
    FRESH = "FRESH"
    STALE = "STALE"
    STATIC = "STATIC"
    UNKNOWN = "UNKNOWN"

class Severity(str, Enum):
    LOW = "LOW"
    MODERATE = "MODERATE"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"

class ConfidenceLevel(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"

class IncidentStatus(str, Enum):
    RECEIVED = "RECEIVED"
    INTERPRETING = "INTERPRETING"
    ACTIVE_UNCONFIRMED = "ACTIVE_UNCONFIRMED"
    RESPONSE_PROPOSED = "RESPONSE_PROPOSED"
    AWAITING_APPROVAL = "AWAITING_APPROVAL"
    RESPONSE_ACTIVE = "RESPONSE_ACTIVE"
    EN_ROUTE = "EN_ROUTE"
    ON_SCENE = "ON_SCENE"
    TRANSPORT_ACTIVE = "TRANSPORT_ACTIVE"
    HANDOVER = "HANDOVER"
    CLOSED = "CLOSED"
    REQUIRES_REVIEW = "REQUIRES_REVIEW"
    DUPLICATE_MERGED = "DUPLICATE_MERGED"
    CANCELLED_FALSE_REPORT = "CANCELLED_FALSE_REPORT"

class ResourceType(str, Enum):
    AMBULANCE = "AMBULANCE"
    FIRE_RESCUE = "FIRE_RESCUE"

class ResourceStatus(str, Enum):
    AVAILABLE = "AVAILABLE"
    RESERVED = "RESERVED"
    ASSIGNED = "ASSIGNED"
    EN_ROUTE = "EN_ROUTE"
    ON_SCENE = "ON_SCENE"
    TRANSPORTING = "TRANSPORTING"
    OUT_OF_SERVICE = "OUT_OF_SERVICE"

class ResponsePlanStatus(str, Enum):
    CANDIDATE = "CANDIDATE"
    RECOMMENDED = "RECOMMENDED"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    SUPERSEDED = "SUPERSEDED"
```

---

# 9. Core Phase-01 Contracts

```python
class Coordinate(BaseModel):
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)

class ProvenanceMetadata(BaseModel):
    source: str
    data_reality: DataReality
    last_updated: datetime
    freshness_status: FreshnessStatus
    source_reference: str | None = None

class ResourceRequirement(BaseModel):
    resource_type: ResourceType
    count: int = Field(ge=1, le=5)

class ManualIncidentCreate(BaseModel):
    incident_type: str
    severity: Severity
    confidence_level: ConfidenceLevel = ConfidenceLevel.HIGH
    location: Coordinate
    location_text: str | None = None
    casualty_count: int | None = Field(default=None, ge=0)
    casualty_range: str | None = None
    trapped_person: bool | None = None
    road_blockage: bool | None = None
    required_resources: list[ResourceRequirement]
    operator_reference: str = "demo-operator"

class ApprovePlanRequest(BaseModel):
    expected_incident_version: int
    expected_plan_version: int
    operator_reference: str = "demo-operator"
```

`required_resources` must contain at least one requirement.

---

# 10. Phase-01 Endpoint Set

Prefix all with `/api/v1`.

```text
GET  /health
POST /intake/manual
GET  /incidents
GET  /incidents/{incident_id}
GET  /resources
GET  /resources/{resource_id}
POST /incidents/{incident_id}/plans/generate
GET  /incidents/{incident_id}/plans
GET  /plans/{plan_id}
POST /plans/{plan_id}/approve
GET  /map/boundary
GET  /map/roads
GET  /map/zones
GET  /map/hospitals
POST /routes/preview
```

Do not create placeholder endpoints for later phases.

---

# 11. Task 1 — FastAPI Runtime + Config Foundation

**Files:** `backend/app/__init__.py`, `config.py`, `main.py`, `requirements.txt`, `.env.example`, `tests/test_health.py`

Write failing test first:

```python
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_health():
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "SirenGrid API",
        "api_version": "v1",
    }
```

Implement compact settings:

```text
APP_NAME = SirenGrid API
API_PREFIX = /api/v1
DATABASE_URL default = sqlite:///./sirengrid.db
CORS origins configurable
MAX_ROUTE_SNAP_DISTANCE_M = 1500.0
NASR_CITY_DATA_DIR
```

Run focused test and Ruff.

Commit: `feat: add SirenGrid FastAPI runtime`

---

# 12. Task 2 — SQLite WAL + Test Isolation

**Files:** `backend/app/db.py`, `backend/tests/conftest.py`, `backend/tests/test_db.py`

Expose:

```python
Base
engine
SessionLocal
get_db()
init_db()
```

SQLite must enable:

```sql
PRAGMA foreign_keys=ON;
PRAGMA journal_mode=WAL;
```

Use `connect_args={"check_same_thread": False}`.

Tests must use an isolated temporary DB.

Commit: `feat: add SQLite operational persistence`

---

# 13. Task 3 — Shared Schemas + SQLAlchemy Models

**Files:** `backend/app/schemas.py`, `backend/app/models.py`, `backend/tests/test_schemas.py`

Models:
- Incident
- EmergencyResource
- ResponsePlan
- Approval
- TimelineEvent

Incident minimum fields:

```text
id UUID
version int starts 1
incident_type
severity
confidence_level
status
latitude
longitude
location_text nullable
casualty_count nullable
casualty_range nullable
trapped_person nullable
road_blockage nullable
required_resources_json
current_plan_id nullable
created_at
updated_at
provenance_json
```

Resource minimum fields:

```text
id
version
name
resource_type
capability_tags_json
status
latitude
longitude
home_zone nullable
assigned_incident_id nullable
last_updated
provenance_json
```

ResponsePlan minimum fields:

```text
id
incident_id
incident_version
plan_version
status
resource_ids_json
routes_json
metrics_json
score_breakdown_json
created_at
```

Approval minimum fields:

```text
id
plan_id
incident_id
operator_reference
action
expected_incident_version
expected_plan_version
created_at
```

Tests must cover invalid coordinates, unknown casualty count, severity/confidence distinction, UNKNOWN freshness, exact resource statuses, non-empty requirements.

Commit: `feat: define SirenGrid core contracts and models`

---

# 14. Task 4 — Import Nasr City Donor Assets

Populate `data/processed/nasr_city/` from the pinned donor.

Required:

```text
nasr_city_boundary.geojson
nasr_city_grid_500m.geojson
nasr_city_graph.graphml
nasr_city_emergency_facilities.geojson
provenance.json
```

Provenance must state:

```text
source_repo = MahmoudNagiubX/Egypt-Smart-City-Digital-Twin
source_commit = 93ca9e90e2fc52c914dd5ccbe42bdc84ce745d3d
data_reality = REAL_DERIVED
freshness_status = STATIC
purpose = Phase 01 Nasr City geospatial bootstrap
refresh_policy = bootstrap only; refresh current OSM/Geofabrik/Overpass in Phase 02
```

Tests: all required assets exist and are non-empty; GeoJSON layers are non-empty FeatureCollections.

Commit: `data: import Nasr City bootstrap geospatial assets`

---

# 15. Task 5 — Base OSM Routing Engine

**Files:** `backend/app/routing.py`, `backend/tests/test_routing.py`

Implement:

```python
class RoutingPointOutsideGraphError(ValueError):
    pass

class RouteNotFoundError(ValueError):
    pass

def load_routing_graph(): ...
def haversine_distance_m(lon1, lat1, lon2, lat2) -> float: ...
def snap_coordinate_to_graph(graph, coordinate, max_distance_m) -> tuple[int, float]: ...
def compute_route_on_graph(graph, origin, destination): ...
```

Use base OSM travel time only.

Travel-time source label:

`OSM_BASE_TRAVEL_TIME`

Failure behavior:
- coordinate >1500m from graph → error,
- same snapped node → error,
- no path → error,
- missing GraphML → error.

Never return zero ETA/distance as a fake success.

TDD:
- tiny synthetic graph chooses lower travel-time path,
- distance sums correctly,
- no path rejected,
- same node rejected,
- real GraphML loads,
- one Nasr City route computes.

Commit: `feat: add real Nasr City base routing`

---

# 16. Task 6 — Manual Operator Intake

**Files:** `backend/app/incidents.py`, `backend/app/main.py`, `backend/tests/test_incidents.py`

Endpoint:

`POST /api/v1/intake/manual`

Sequence:
1. validate operator input,
2. create incident UUID,
3. status = `ACTIVE_UNCONFIRMED`,
4. version = 1,
5. unknown fields remain null,
6. provenance = operator manual entry / simulated demo world / fresh,
7. timeline event `INCIDENT_CREATED`,
8. commit and return incident.

Tests:
- one report activates immediately,
- no second report required,
- unknown casualty remains null,
- invalid coordinate rejected,
- empty required resources rejected.

Commit: `feat: add manual control-room incident intake`

---

# 17. Task 7 — Simulated Resource State + Seed

**Files:** `backend/app/resources.py`, `backend/app/seed.py`, `data/scenarios/phase01_resources.json`, `backend/tests/test_resources.py`

Seed at least:
- 3 ambulances,
- 2 fire/rescue units.

All coordinates must be verified to snap acceptably to the Nasr City graph.

All operational resource state is labeled `SIMULATED`.

Support:

```powershell
python -m app.seed
```

Seed command must be idempotent.

Endpoints:

```text
GET /api/v1/resources
GET /api/v1/resources/{id}
```

Tests:
- no duplicates after second seed,
- statuses/provenance correct,
- unavailable/assigned units are excluded from planner eligibility.

Commit: `feat: add simulated responder state`

---

# 18. Task 8 — Minimal Candidate Plan Generator

**Files:** `backend/app/planning.py`, `backend/tests/test_planning.py`

Endpoint:

`POST /api/v1/incidents/{incident_id}/plans/generate`

Algorithm for each operator-supplied requirement:
1. query only `AVAILABLE` and unassigned matching resources,
2. compute real base OSM route from every eligible resource to incident,
3. exclude resources with no route,
4. sort by ETA ascending,
5. select requested count,
6. never reuse same resource twice,
7. fail clearly if not enough eligible/routeable resources.

Metrics:

```json
{
  "max_arrival_eta_seconds": 0,
  "mean_arrival_eta_seconds": 0,
  "selected_resource_count": 0,
  "routing_source": "OSM_BASE_TRAVEL_TIME"
}
```

Use actual calculated values.

Score breakdown:

```json
{
  "algorithm": "MIN_BASE_ROUTE_ETA_WITH_HARD_AVAILABILITY_CONSTRAINTS",
  "coverage_considered": false,
  "traffic_source": "OSM_BASE_TRAVEL_TIME",
  "note": "Phase 01 minimal plan. Coverage-aware optimization arrives in Phase 04."
}
```

Plan status = `RECOMMENDED`.
Incident status → `AWAITING_APPROVAL`.
Increment incident version exactly once.
Append `PLAN_GENERATED` timeline event.

Tests:
- chooses lower ETA available resource,
- ignores unavailable closer resource,
- respects type/count,
- insufficient resources fails,
- route failure makes resource infeasible,
- route geometry/ETA present,
- version/state changes exact.

Commit: `feat: generate minimal real response plans`

---

# 19. Task 9 — Version-Checked Transactional Approval

**Files:** `backend/app/planning.py`, `backend/tests/test_approval.py`

Endpoint:

`POST /api/v1/plans/{plan_id}/approve`

Verify before mutation:
1. plan exists,
2. incident exists,
3. plan status `RECOMMENDED`,
4. incident status `AWAITING_APPROVAL`,
5. expected incident version matches,
6. expected plan version matches,
7. every selected resource remains AVAILABLE,
8. every selected resource remains unassigned.

Any stale/conflict condition → HTTP 409.

One DB transaction must:
- set plan APPROVED,
- set incident RESPONSE_ACTIVE,
- increment incident version,
- set resources ASSIGNED + incident id,
- increment resource versions,
- insert Approval row,
- append approval/assignment timeline events,
- commit once.

Repeated approval must not double-assign.
Recommended behavior: HTTP 409 `PLAN_ALREADY_APPROVED`.

Tests:
- valid approval,
- repeat rejected,
- stale incident version rejected,
- stale plan version rejected,
- resource changed before approval → entire transaction fails,
- already-assigned resource cannot be selected later.

Commit: `feat: add safe versioned plan approval`

---

# 20. Task 10 — Map + Route Preview APIs

Endpoints:

```text
GET /api/v1/map/boundary
GET /api/v1/map/roads
GET /api/v1/map/zones
GET /api/v1/map/hospitals
POST /api/v1/routes/preview
```

Every map response returns:

```text
layer
geojson
provenance
```

Route preview must reuse the same routing engine as planning.

HTTP mapping:
- outside graph → 422,
- same-node → 422,
- no path → 409,
- missing configured asset → 503.

Tests must confirm no fake live traffic labels.

Commit: `feat: expose Phase 01 map and route contracts`

---

# 21. Task 11 — Frontend-Agnostic Contract Examples

Do not create frontend code.

Ensure `/openapi.json` exposes examples/schemas for:
- manual intake,
- incident read,
- resource read,
- candidate plan,
- approval request/result,
- map response,
- route preview.

Optionally add `docs/contracts/phase01_example_payloads.json` only if the frontend owner requests a static fixture.

Commit: `docs: publish Phase 01 API contract examples`

---

# 22. Task 12 — Golden Flow Integration Test

**File:** `backend/tests/test_golden_flow.py`

Required sequence:
1. clean DB,
2. seed resources,
3. create manual incident,
4. assert ACTIVE_UNCONFIRMED,
5. generate plan,
6. assert real resources selected,
7. route geometry exists + ETA >0,
8. incident AWAITING_APPROVAL,
9. approve exact current version,
10. plan APPROVED,
11. incident RESPONSE_ACTIVE,
12. resources ASSIGNED,
13. resources reference incident,
14. timeline has creation/generation/approval,
15. repeat approval does not double assign.

This is the Phase-01 exit gate.

Commit: `test: cover Phase 01 golden flow`

---

# 23. Full Verification

Codex owns the final review.

```powershell
cd backend
python -m pytest -q
python -m ruff check .
python -m compileall app
python -m app.seed
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

One worker only.

Manual smoke:

```text
GET  /api/v1/health
GET  /api/v1/map/boundary
GET  /api/v1/resources
POST /api/v1/intake/manual
POST /api/v1/incidents/{id}/plans/generate
GET  /api/v1/plans/{id}
POST /api/v1/plans/{id}/approve
GET  /api/v1/incidents/{id}
GET  /api/v1/resources/{assigned_id}
```

Confirm:
- route is real graph geometry,
- ETA >0 and base OSM labeled,
- resource state changes only after approval,
- no AI extraction call,
- no TomTom/live traffic claim,
- simulation/reality labels honest.

---

# 24. Codex Final Review Report

```text
PHASE 01 REVIEW

Phase 00 baseline clean:
Architecture v1.1 compliance:
Master Plan v1.2 compliance:

Implemented:
Files changed:

Manual intake:
Persistence:
Resource state:
Routing:
Candidate planning:
Approval/version safety:
Map/API contracts:
Golden Flow:

Tests:
Ruff:
Compile:
Manual smoke:

Repo reconnaissance performed:
Relevant references:
Files/patterns inspected:
What was reused:
What was rewritten/adapted:
Rejected donor behavior:

Real-vs-simulated audit:
AI disabled audit:
TomTom/live-traffic claim audit:

Not implemented:
Assumptions:
Deviations:
Blocking issues:

Verdict: PASS | FIXES_REQUIRED
```

Do not start Phase 02 before PASS and ChatGPT final review.

---

# 25. Phase 01 Exit Criteria

- [ ] Phase 00 merged before Phase 01 branch.
- [ ] FastAPI backend boots.
- [ ] One-worker rule preserved.
- [ ] SQLite WAL + foreign keys active.
- [ ] Contracts include reality/freshness/version fields.
- [ ] Nasr City donor assets imported with provenance.
- [ ] OSM GraphML route engine works.
- [ ] Manual control-room incident can be created immediately.
- [ ] Simulated resources exist and are clearly labeled.
- [ ] Only AVAILABLE/unassigned resources are eligible.
- [ ] Candidate plan contains real OSM route metrics.
- [ ] Operator approval is version checked.
- [ ] Approval + resource assignment is transactional.
- [ ] Repeated/stale approval cannot double assign.
- [ ] Map APIs return real-derived static content.
- [ ] OpenAPI is frontend-consumable.
- [ ] Golden Flow E2E passes.
- [ ] Full tests pass.
- [ ] Ruff passes.
- [ ] Compilation passes.
- [ ] No AI structured extraction called.
- [ ] No TomTom/live traffic claim made.
- [ ] Codex verdict PASS.
- [ ] ChatGPT final architecture/product review PASS.

---

# 26. Suggested Prompt to Codex

```text
We are starting SirenGrid Phase 01 after a successful Phase 00.

Read in this exact order:
1. AGENTS.md
2. docs/MASTER_PLAN.md v1.2
3. docs/DATA_LIST.md
4. docs/DECISIONS.md
5. docs/TECHNICAL_ARCHITECTURE_PLAN.md v1.1
6. docs/PHASE_00_FEASIBILITY_REPORT.md
7. docs/phases/PHASE_01_FOUNDATION_AND_GOLDEN_FLOW.md

First verify:
- Phase 00 is committed/merged into the baseline.
- Technical Architecture v1.1 is locked.
- PD-006 through PD-015 are present.
- structured AI extraction remains disabled/default-off.
- frontend stack is still deferred.

You are the senior task verifier and code reviewer.
Execute Phase 01 only.

Use agy-delegate to give Antigravity one bounded implementation task at a time.

Before non-trivial implementation, enforce the repo-reconnaissance sections of the Phase 01 plan.

Primary direct donor:
MahmoudNagiubX/Egypt-Smart-City-Digital-Twin
Pinned Phase-01 reference commit:
93ca9e90e2fc52c914dd5ccbe42bdc84ce745d3d

Selective reference:
ashwinnm13/ResQPath

Do not copy weather-specific behavior.
Do not copy ResQPath's unavailable-resource fallback.
Do not convert route failures to zero metrics.
Do not add OpenRouteService.
Do not integrate AI structured extraction.
Do not integrate TomTom.
Do not implement coverage/hospital/corridor/replanning/WebSocket.
Do not lock or implement the frontend stack.

Require a failing test before behavioral implementation where practical, then implement minimum code, rerun the focused test, and keep the full suite green.

After every bounded task, inspect the worker result before moving on.

After all tasks:
- inspect the full diff yourself,
- run full pytest,
- run Ruff,
- run compileall,
- run the manual Golden Flow smoke,
- audit real-vs-simulated labels,
- audit version/idempotency approval behavior,
- produce the required PHASE 01 REVIEW.

If FIXES_REQUIRED, delegate only bounded fixes and re-review.
Do not start Phase 02.
```

---

# 27. What Comes Next

Only after Phase 01 PASS:

`Phase 02 — Geospatial + Traffic Runtime`

Phase 02 refreshes road/infrastructure data and integrates TomTom as a versioned, confidence-aware traffic overlay without mutating base graph truth.

Phase 01's job is to make sure SirenGrid already works end-to-end before adding those complexities.

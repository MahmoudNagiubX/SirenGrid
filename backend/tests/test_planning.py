from __future__ import annotations

from typing import Any
import uuid

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

import app.models as _models  # noqa: F401
from app.db import init_db
from app.main import app
from app.models import EmergencyResource, Incident, ResponsePlan, TimelineEvent
from app.routing import (
    RouteNotFoundError,
    RouteResult,
    RoutingPointOutsideGraphError,
)
from app.schemas import (
    ConfidenceLevel,
    IncidentStatus,
    ResourceStatus,
    ResourceType,
    ResponsePlanStatus,
    Severity,
)
from app.seed import seed_resources


@pytest.fixture(autouse=True)
def setup_isolated_db_tables(isolated_engine: Engine) -> None:
    """Initialize all model tables on the isolated test engine."""
    init_db(isolated_engine)


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def create_test_incident(
    db: Session,
    incident_id: str | None = None,
    version: int = 1,
    status: IncidentStatus = IncidentStatus.ACTIVE_UNCONFIRMED,
    lat: float = 30.0561,
    lon: float = 31.3452,
    required_resources: list[dict[str, Any]] | None = None,
) -> Incident:
    if incident_id is None:
        incident_id = str(uuid.uuid4())
    if required_resources is None:
        required_resources = [{"resource_type": "AMBULANCE", "count": 1}]
    inc = Incident(
        id=incident_id,
        version=version,
        incident_type="traffic_collision",
        severity=Severity.HIGH,
        confidence_level=ConfidenceLevel.HIGH,
        status=status,
        latitude=lat,
        longitude=lon,
        location_text="El-Nasr Rd & Abbas El-Akkad",
        casualty_count=2,
        required_resources_json=required_resources,
        current_plan_id=None,
        provenance_json={"source": "test_harness"},
    )
    db.add(inc)
    db.commit()
    db.refresh(inc)
    return inc


def create_test_resource(
    db: Session,
    resource_id: str,
    name: str,
    resource_type: ResourceType = ResourceType.AMBULANCE,
    status: ResourceStatus = ResourceStatus.AVAILABLE,
    lat: float = 30.0600,
    lon: float = 31.3400,
    assigned_incident_id: str | None = None,
) -> EmergencyResource:
    res = EmergencyResource(
        id=resource_id,
        version=1,
        name=name,
        resource_type=resource_type,
        status=status,
        latitude=lat,
        longitude=lon,
        assigned_incident_id=assigned_incident_id,
        capability_tags_json=["BLS"],
        provenance_json={"source": "test_harness"},
    )
    db.add(res)
    db.commit()
    db.refresh(res)
    return res


def make_mock_route_result(
    distance_m: float,
    eta_seconds: float,
    routing_source: str = "OSM_BASE_TRAVEL_TIME",
) -> RouteResult:
    return RouteResult(
        nodes=[101, 102],
        geometry={
            "type": "LineString",
            "coordinates": [[31.3300, 30.0500], [31.3452, 30.0561]],
        },
        distance_m=distance_m,
        eta_seconds=eta_seconds,
        origin_snap_distance_m=10.5,
        destination_snap_distance_m=12.2,
        routing_source=routing_source,
    )


def test_generate_plan_missing_incident_returns_404(client: TestClient) -> None:
    """A clear 404 is required when generating a plan for a nonexistent incident."""
    random_id = str(uuid.uuid4())
    response = client.post(f"/api/v1/incidents/{random_id}/plans/generate")
    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


def test_generate_plan_chooses_lower_eta_available_resource(
    client: TestClient,
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Algorithm must sort routeable candidates by eta_seconds ascending and pick the lowest ETA."""
    incident = create_test_incident(
        db=db_session,
        required_resources=[{"resource_type": "AMBULANCE", "count": 1}],
    )

    # Resource A: further away in travel time (ETA 300s, distance 1500m)
    create_test_resource(
        db=db_session,
        resource_id="res-amb-slow",
        name="Slow Ambulance",
        resource_type=ResourceType.AMBULANCE,
        status=ResourceStatus.AVAILABLE,
        lat=30.0610,
        lon=31.3410,
    )
    # Resource B: faster arrival (ETA 120s, distance 2000m)
    create_test_resource(
        db=db_session,
        resource_id="res-amb-fast",
        name="Fast Ambulance",
        resource_type=ResourceType.AMBULANCE,
        status=ResourceStatus.AVAILABLE,
        lat=30.0620,
        lon=31.3420,
    )

    # Mock routing based on candidate resource coordinates
    def mock_compute(graph: Any, origin: Any, destination: Any) -> RouteResult:
        if abs(origin.lat - 30.0620) < 1e-4:
            return make_mock_route_result(distance_m=2000.0, eta_seconds=120.0)
        return make_mock_route_result(distance_m=1500.0, eta_seconds=300.0)

    monkeypatch.setattr("app.planning.load_routing_graph", lambda: None)
    monkeypatch.setattr("app.planning.compute_route_on_graph", mock_compute)

    response = client.post(f"/api/v1/incidents/{incident.id}/plans/generate")
    assert response.status_code == 201, response.text
    data = response.json()

    assert data["resource_ids"] == ["res-amb-fast"]
    assert len(data["routes"]) == 1
    assert data["routes"][0]["resource_id"] == "res-amb-fast"
    assert data["routes"][0]["eta_seconds"] == 120.0
    assert data["metrics"]["max_arrival_eta_seconds"] == 120.0
    assert data["metrics"]["mean_arrival_eta_seconds"] == 120.0
    assert data["metrics"]["selected_resource_count"] == 1


def test_generate_plan_ignores_closer_unavailable_or_assigned_resources(
    client: TestClient,
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Closer unavailable or assigned resources must never be considered by the planner."""
    incident = create_test_incident(
        db=db_session,
        required_resources=[{"resource_type": "AMBULANCE", "count": 1}],
    )

    # Resource 1: AVAILABLE but assigned to another incident (ETA 50s)
    create_test_resource(
        db=db_session,
        resource_id="res-amb-assigned-avail",
        name="Assigned but Available Ambulance",
        resource_type=ResourceType.AMBULANCE,
        status=ResourceStatus.AVAILABLE,
        assigned_incident_id="other-inc-01",
        lat=30.0570,
        lon=31.3460,
    )
    # Resource 2: Status ASSIGNED (ETA 60s)
    create_test_resource(
        db=db_session,
        resource_id="res-amb-assigned-status",
        name="Assigned Status Ambulance",
        resource_type=ResourceType.AMBULANCE,
        status=ResourceStatus.ASSIGNED,
        assigned_incident_id="other-inc-02",
        lat=30.0580,
        lon=31.3470,
    )
    # Resource 3: OUT_OF_SERVICE (ETA 70s)
    create_test_resource(
        db=db_session,
        resource_id="res-amb-oos",
        name="OOS Ambulance",
        resource_type=ResourceType.AMBULANCE,
        status=ResourceStatus.OUT_OF_SERVICE,
        lat=30.0590,
        lon=31.3480,
    )
    # Resource 4: AVAILABLE and unassigned (ETA 250s)
    create_test_resource(
        db=db_session,
        resource_id="res-amb-eligible",
        name="Eligible Available Ambulance",
        resource_type=ResourceType.AMBULANCE,
        status=ResourceStatus.AVAILABLE,
        assigned_incident_id=None,
        lat=30.0650,
        lon=31.3500,
    )

    def mock_compute(graph: Any, origin: Any, destination: Any) -> RouteResult:
        return make_mock_route_result(distance_m=1000.0, eta_seconds=250.0)

    monkeypatch.setattr("app.planning.load_routing_graph", lambda: None)
    monkeypatch.setattr("app.planning.compute_route_on_graph", mock_compute)

    response = client.post(f"/api/v1/incidents/{incident.id}/plans/generate")
    assert response.status_code == 201, response.text
    data = response.json()

    assert data["resource_ids"] == ["res-amb-eligible"]
    assert data["metrics"]["selected_resource_count"] == 1


def test_generate_plan_respects_resource_type_and_count_and_never_reuses_resource(
    client: TestClient,
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Plan must satisfy exact counts for each type and never reuse the same resource twice."""
    incident = create_test_incident(
        db=db_session,
        required_resources=[
            {"resource_type": "AMBULANCE", "count": 2},
            {"resource_type": "FIRE_RESCUE", "count": 1},
        ],
    )

    create_test_resource(db_session, "amb-1", "Amb 1", ResourceType.AMBULANCE, lat=30.01)
    create_test_resource(db_session, "amb-2", "Amb 2", ResourceType.AMBULANCE, lat=30.02)
    create_test_resource(db_session, "amb-3", "Amb 3", ResourceType.AMBULANCE, lat=30.03)

    create_test_resource(db_session, "fire-1", "Fire 1", ResourceType.FIRE_RESCUE, lat=30.04)
    create_test_resource(db_session, "fire-2", "Fire 2", ResourceType.FIRE_RESCUE, lat=30.05)

    eta_map = {
        30.01: 300.0,
        30.02: 100.0,
        30.03: 200.0,
        30.04: 150.0,
        30.05: 250.0,
    }

    def mock_compute(graph: Any, origin: Any, destination: Any) -> RouteResult:
        eta = eta_map.get(round(origin.lat, 2), 500.0)
        return make_mock_route_result(distance_m=eta * 10, eta_seconds=eta)

    monkeypatch.setattr("app.planning.load_routing_graph", lambda: None)
    monkeypatch.setattr("app.planning.compute_route_on_graph", mock_compute)

    response = client.post(f"/api/v1/incidents/{incident.id}/plans/generate")
    assert response.status_code == 201, response.text
    data = response.json()

    # Ambulances selected should be amb-2 (100s) and amb-3 (200s), Fire rescue should be fire-1 (150s)
    expected_ids = ["amb-2", "amb-3", "fire-1"]
    assert sorted(data["resource_ids"]) == sorted(expected_ids)
    assert len(data["resource_ids"]) == 3
    # Verify no duplicate IDs
    assert len(set(data["resource_ids"])) == 3
    assert data["metrics"]["selected_resource_count"] == 3


def test_generate_plan_insufficient_eligible_resources_fails_without_mutation(
    client: TestClient,
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When eligible resources < required count, request fails clearly and incident remains unchanged."""
    incident = create_test_incident(
        db=db_session,
        required_resources=[{"resource_type": "FIRE_RESCUE", "count": 2}],
    )

    # Only 1 fire rescue available
    create_test_resource(
        db=db_session,
        resource_id="fire-lone",
        name="Lone Fire Unit",
        resource_type=ResourceType.FIRE_RESCUE,
        status=ResourceStatus.AVAILABLE,
    )

    def mock_compute(graph: Any, origin: Any, destination: Any) -> RouteResult:
        return make_mock_route_result(distance_m=1000.0, eta_seconds=180.0)

    monkeypatch.setattr("app.planning.load_routing_graph", lambda: None)
    monkeypatch.setattr("app.planning.compute_route_on_graph", mock_compute)

    response = client.post(f"/api/v1/incidents/{incident.id}/plans/generate")
    assert response.status_code in (409, 422), response.text
    detail = response.json()["detail"].lower()
    assert "insufficient" in detail or "eligible" in detail or "resource" in detail

    # Verify incident was NOT mutated
    db_session.expire_all()
    reloaded_inc = db_session.get(Incident, incident.id)
    assert reloaded_inc is not None
    assert reloaded_inc.version == 1
    assert reloaded_inc.status == IncidentStatus.ACTIVE_UNCONFIRMED
    assert reloaded_inc.current_plan_id is None

    # Verify no plan was persisted
    plans = db_session.scalars(select(ResponsePlan).where(ResponsePlan.incident_id == incident.id)).all()
    assert len(plans) == 0

    # Verify no PLAN_GENERATED timeline event was inserted
    events = db_session.scalars(
        select(TimelineEvent).where(
            TimelineEvent.incident_id == incident.id,
            TimelineEvent.event_type == "PLAN_GENERATED",
        )
    ).all()
    assert len(events) == 0


def test_generate_plan_route_failure_makes_candidate_infeasible_and_fails_if_no_alternative(
    client: TestClient,
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Route failure makes a candidate infeasible; if fewer routeable candidates remain, fail clearly."""
    incident = create_test_incident(
        db=db_session,
        required_resources=[{"resource_type": "AMBULANCE", "count": 1}],
    )

    create_test_resource(
        db=db_session,
        resource_id="amb-unrouteable",
        name="Unrouteable Ambulance",
        resource_type=ResourceType.AMBULANCE,
        status=ResourceStatus.AVAILABLE,
    )

    def mock_compute(graph: Any, origin: Any, destination: Any) -> RouteResult:
        raise RouteNotFoundError("No path exists between nodes")

    monkeypatch.setattr("app.planning.load_routing_graph", lambda: None)
    monkeypatch.setattr("app.planning.compute_route_on_graph", mock_compute)

    response = client.post(f"/api/v1/incidents/{incident.id}/plans/generate")
    assert response.status_code in (409, 422), response.text

    # Verify incident state unmutated
    db_session.expire_all()
    inc = db_session.get(Incident, incident.id)
    assert inc is not None
    assert inc.version == 1
    assert inc.status == IncidentStatus.ACTIVE_UNCONFIRMED


def test_generate_plan_route_failure_falls_back_to_other_routeable_candidate(
    client: TestClient,
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """If one candidate fails routing, planner continues to evaluate other routeable candidates."""
    incident = create_test_incident(
        db=db_session,
        required_resources=[{"resource_type": "AMBULANCE", "count": 1}],
    )

    create_test_resource(
        db=db_session,
        resource_id="amb-broken",
        name="Broken Path Ambulance",
        resource_type=ResourceType.AMBULANCE,
        status=ResourceStatus.AVAILABLE,
        lat=30.0700,
        lon=31.3500,
    )
    create_test_resource(
        db=db_session,
        resource_id="amb-working",
        name="Working Path Ambulance",
        resource_type=ResourceType.AMBULANCE,
        status=ResourceStatus.AVAILABLE,
        lat=30.0800,
        lon=31.3600,
    )

    def mock_compute(graph: Any, origin: Any, destination: Any) -> RouteResult:
        if abs(origin.lat - 30.0700) < 1e-4:
            raise RoutingPointOutsideGraphError("Coordinate too far from graph")
        return make_mock_route_result(distance_m=1200.0, eta_seconds=160.0)

    monkeypatch.setattr("app.planning.load_routing_graph", lambda: None)
    monkeypatch.setattr("app.planning.compute_route_on_graph", mock_compute)

    response = client.post(f"/api/v1/incidents/{incident.id}/plans/generate")
    assert response.status_code == 201, response.text
    data = response.json()

    assert data["resource_ids"] == ["amb-working"]


def test_generate_plan_metrics_score_breakdown_routes_and_timeline_contracts(
    client: TestClient,
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify exact metrics keys, score breakdown semantics, routes geometry, and timeline event."""
    incident = create_test_incident(
        db=db_session,
        required_resources=[
            {"resource_type": "AMBULANCE", "count": 1},
            {"resource_type": "FIRE_RESCUE", "count": 1},
        ],
    )

    create_test_resource(
        db=db_session,
        resource_id="res-amb-01",
        name="Ambulance Alpha",
        resource_type=ResourceType.AMBULANCE,
        status=ResourceStatus.AVAILABLE,
        lat=30.0610,
        lon=31.3410,
    )
    create_test_resource(
        db=db_session,
        resource_id="res-fire-01",
        name="Fire Rescue Bravo",
        resource_type=ResourceType.FIRE_RESCUE,
        status=ResourceStatus.AVAILABLE,
        lat=30.0620,
        lon=31.3420,
    )

    def mock_compute(graph: Any, origin: Any, destination: Any) -> RouteResult:
        if abs(origin.lat - 30.0610) < 1e-4:
            return make_mock_route_result(distance_m=1000.0, eta_seconds=100.0)
        return make_mock_route_result(distance_m=2000.0, eta_seconds=200.0)

    monkeypatch.setattr("app.planning.load_routing_graph", lambda: None)
    monkeypatch.setattr("app.planning.compute_route_on_graph", mock_compute)

    response = client.post(f"/api/v1/incidents/{incident.id}/plans/generate")
    assert response.status_code == 201, response.text
    data = response.json()

    # Plan top-level properties
    assert uuid.UUID(data["id"])
    assert data["incident_id"] == incident.id
    assert data["incident_version"] == 2  # matches post-generation incident version
    assert data["plan_version"] == 1
    assert data["status"] == ResponsePlanStatus.RECOMMENDED.value

    # Metrics JSON verification
    metrics = data["metrics"]
    assert metrics["max_arrival_eta_seconds"] == 200.0
    assert metrics["mean_arrival_eta_seconds"] == 150.0
    assert metrics["selected_resource_count"] == 2
    assert metrics["routing_source"] == "OSM_BASE_TRAVEL_TIME"

    # Score breakdown JSON verification
    expected_score = {
        "algorithm": "MIN_BASE_ROUTE_ETA_WITH_HARD_AVAILABILITY_CONSTRAINTS",
        "coverage_considered": False,
        "traffic_source": "OSM_BASE_TRAVEL_TIME",
        "note": "Phase 01 minimal plan. Coverage-aware optimization arrives in Phase 04.",
    }
    assert data["score_breakdown"] == expected_score

    # Routes JSON verification
    assert len(data["routes"]) == 2
    for r in data["routes"]:
        assert r["resource_id"] in ["res-amb-01", "res-fire-01"]
        assert r["resource_type"] in ["AMBULANCE", "FIRE_RESCUE"]
        assert r["resource_name"] in ["Ambulance Alpha", "Fire Rescue Bravo"]
        assert r["origin"]["lat"] > 0
        assert r["destination"]["lat"] == incident.latitude
        assert r["destination"]["lon"] == incident.longitude
        assert r["route_geometry"]["type"] == "LineString"
        assert len(r["route_geometry"]["coordinates"]) >= 2
        assert r["distance_m"] > 0
        assert r["eta_seconds"] > 0
        assert r["origin_snap_distance_m"] >= 0
        assert r["destination_snap_distance_m"] >= 0
        assert r["routing_source"] == "OSM_BASE_TRAVEL_TIME"

    # DB Incident state verification
    db_session.expire_all()
    inc = db_session.get(Incident, incident.id)
    assert inc is not None
    assert inc.status == IncidentStatus.AWAITING_APPROVAL
    assert inc.version == 2
    assert inc.current_plan_id == data["id"]

    # DB TimelineEvent verification
    events = db_session.scalars(
        select(TimelineEvent).where(
            TimelineEvent.incident_id == incident.id,
            TimelineEvent.event_type == "PLAN_GENERATED",
        )
    ).all()
    assert len(events) == 1
    event = events[0]
    assert event.details_json["plan_id"] == data["id"]
    assert event.details_json["selected_resource_count"] == 2
    assert event.details_json["routing_source"] == "OSM_BASE_TRAVEL_TIME"


def test_generate_plan_repeated_generation_increments_plan_version(
    client: TestClient,
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Repeated plan generation safely increments plan_version and updates incident current_plan_id."""
    incident = create_test_incident(
        db=db_session,
        required_resources=[{"resource_type": "AMBULANCE", "count": 1}],
    )

    create_test_resource(
        db=db_session,
        resource_id="amb-repeat",
        name="Ambulance Repeat",
        resource_type=ResourceType.AMBULANCE,
        status=ResourceStatus.AVAILABLE,
    )

    def mock_compute(graph: Any, origin: Any, destination: Any) -> RouteResult:
        return make_mock_route_result(distance_m=1000.0, eta_seconds=120.0)

    monkeypatch.setattr("app.planning.load_routing_graph", lambda: None)
    monkeypatch.setattr("app.planning.compute_route_on_graph", mock_compute)

    # First generation
    resp1 = client.post(f"/api/v1/incidents/{incident.id}/plans/generate")
    assert resp1.status_code == 201
    plan1 = resp1.json()
    assert plan1["plan_version"] == 1
    assert plan1["incident_version"] == 2
    assert plan1["status"] == ResponsePlanStatus.RECOMMENDED.value

    db_session.expire_all()
    inc1 = db_session.get(Incident, incident.id)
    assert inc1 is not None
    assert inc1.version == 2
    assert inc1.current_plan_id == plan1["id"]

    # Second generation
    resp2 = client.post(f"/api/v1/incidents/{incident.id}/plans/generate")
    assert resp2.status_code == 201
    plan2 = resp2.json()
    assert plan2["plan_version"] == 2
    assert plan2["incident_version"] == 3
    assert plan2["status"] == ResponsePlanStatus.RECOMMENDED.value
    assert plan2["id"] != plan1["id"]

    db_session.expire_all()
    inc2 = db_session.get(Incident, incident.id)
    assert inc2 is not None
    assert inc2.version == 3
    assert inc2.current_plan_id == plan2["id"]

    # Prior current plan must be marked SUPERSEDED
    reloaded_p1 = db_session.get(ResponsePlan, plan1["id"])
    assert reloaded_p1 is not None
    assert reloaded_p1.status == ResponsePlanStatus.SUPERSEDED


def test_generate_plan_real_osm_routing_integration(
    client: TestClient,
    db_session: Session,
) -> None:
    """Integration test exercising real Nasr City GraphML base routing with seeded resources."""
    # Seed standard scenario resources
    seed_resources(db=db_session)

    # Incident located at El-Nasr Road & Abbas El-Akkad
    incident = create_test_incident(
        db=db_session,
        lat=30.0561,
        lon=31.3452,
        required_resources=[
            {"resource_type": "AMBULANCE", "count": 1},
            {"resource_type": "FIRE_RESCUE", "count": 1},
        ],
    )

    # Call real generation without monkeypatching routing
    response = client.post(f"/api/v1/incidents/{incident.id}/plans/generate")
    assert response.status_code == 201, response.text
    data = response.json()

    assert data["incident_id"] == incident.id
    assert data["status"] == ResponsePlanStatus.RECOMMENDED.value
    assert len(data["resource_ids"]) == 2
    assert len(data["routes"]) == 2

    # Verify real geometry and positive distance/travel time from base OSM
    for r in data["routes"]:
        assert r["distance_m"] > 0.0
        assert r["eta_seconds"] > 0.0
        assert r["routing_source"] == "OSM_BASE_TRAVEL_TIME"
        assert r["route_geometry"]["type"] == "LineString"
        assert len(r["route_geometry"]["coordinates"]) >= 2

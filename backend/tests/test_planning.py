from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import Any
import concurrent.futures
import threading
import uuid

from fastapi.testclient import TestClient
import networkx as nx
import pytest
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

import app.models as _models  # noqa: F401
from app import planning
from app.coverage import CoverageZone
from app.db import init_db
from app.main import app
from app.models import EmergencyResource, Incident, ResponsePlan, TimelineEvent
from app.schemas import (
    ConfidenceLevel,
    Coordinate,
    IncidentStatus,
    ResourceStatus,
    ResourceType,
    ResponsePlanStatus,
    Severity,
)
from app.seed import seed_resources

INCIDENT_LAT = 30.0561
INCIDENT_LON = 31.3452


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


def planner_graph(
    responders: Iterable[tuple[str, float, float, float | None]],
) -> Callable[[], nx.MultiDiGraph]:
    """Return a loader for a deterministic star graph around the incident.

    Each entry is ``(node_name, lat, lon, travel_time_seconds)``. Travel time
    becomes the route ETA, so a test expresses intent as an ETA directly. A
    ``None`` travel time adds the node with no edge to the incident, which
    makes that responder genuinely unroutable on the real routing engine.

    The canonical planner routes on this graph, so these tests exercise the
    production routing/coverage/scoring path instead of a mocked route.
    """

    def _load() -> nx.MultiDiGraph:
        graph = nx.MultiDiGraph()
        graph.add_node("incident", x=INCIDENT_LON, y=INCIDENT_LAT)
        for name, lat, lon, travel_time in responders:
            graph.add_node(name, x=lon, y=lat)
            if travel_time is None:
                continue
            for source, target in (("incident", name), (name, "incident")):
                graph.add_edge(
                    source,
                    target,
                    key="0",
                    length=travel_time * 10.0,
                    travel_time=travel_time,
                    base_travel_time_s=travel_time,
                )
        return graph

    return _load


def configure_canonical_planner(
    monkeypatch: pytest.MonkeyPatch,
    graph_loader: Callable[[], nx.MultiDiGraph],
) -> None:
    """Point the canonical planner at a small deterministic world.

    Only the immutable geospatial inputs are substituted. Response-requirement
    resolution, candidate generation, coverage, scoring, ranking, persistence,
    and the concurrency guard all run as they do in production.
    """
    monkeypatch.setattr(planning, "load_routing_graph", graph_loader)
    monkeypatch.setattr(
        planning,
        "load_population_zones",
        lambda _path: (
            CoverageZone(
                zone_id="zone-1",
                centroid=Coordinate(lat=INCIDENT_LAT, lon=INCIDENT_LON),
                population=100.0,
            ),
        ),
    )
    monkeypatch.setattr(
        planning.traffic_runtime,
        "capture_snapshot",
        lambda *_args, **_kwargs: None,
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

    configure_canonical_planner(
        monkeypatch,
        planner_graph(
            [
                ("res-amb-slow", 30.0610, 31.3410, 300.0),
                ("res-amb-fast", 30.0620, 31.3420, 120.0),
            ]
        ),
    )

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

    # The ineligible responders are deliberately the fastest on the graph, so
    # selecting the slower eligible one proves eligibility beats proximity.
    configure_canonical_planner(
        monkeypatch,
        planner_graph(
            [
                ("res-amb-assigned-avail", 30.0570, 31.3460, 50.0),
                ("res-amb-assigned-status", 30.0580, 31.3470, 60.0),
                ("res-amb-oos", 30.0590, 31.3480, 70.0),
                ("res-amb-eligible", 30.0650, 31.3500, 250.0),
            ]
        ),
    )

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

    configure_canonical_planner(
        monkeypatch,
        planner_graph(
            [
                ("amb-1", 30.01, 31.3400, 300.0),
                ("amb-2", 30.02, 31.3400, 100.0),
                ("amb-3", 30.03, 31.3400, 200.0),
                ("fire-1", 30.04, 31.3400, 150.0),
                ("fire-2", 30.05, 31.3400, 250.0),
            ]
        ),
    )

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

    configure_canonical_planner(
        monkeypatch,
        planner_graph([("fire-lone", 30.0600, 31.3400, 180.0)]),
    )

    response = client.post(f"/api/v1/incidents/{incident.id}/plans/generate")
    assert response.status_code in (409, 422), response.text
    detail = response.json()["detail"].lower()
    assert "insufficient" in detail or "eligible" in detail or "resource" in detail or "feasible" in detail

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

    # The only ambulance has no edge to the incident, so it is genuinely
    # unroutable on the real routing engine rather than a mocked failure.
    configure_canonical_planner(
        monkeypatch,
        planner_graph([("amb-unrouteable", 30.0600, 31.3400, None)]),
    )

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

    configure_canonical_planner(
        monkeypatch,
        planner_graph(
            [
                ("amb-broken", 30.0700, 31.3500, None),
                ("amb-working", 30.0800, 31.3600, 160.0),
            ]
        ),
    )

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

    configure_canonical_planner(
        monkeypatch,
        planner_graph(
            [
                ("res-amb-01", 30.0610, 31.3410, 100.0),
                ("res-fire-01", 30.0620, 31.3420, 200.0),
            ]
        ),
    )

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

    # Score breakdown must be the canonical transparent prototype score, not
    # the removed Phase 01 stub. The legacy endpoint is a facade over the
    # canonical planner, so coverage is genuinely considered.
    score = data["score_breakdown"]
    assert score["policy_version"] == "SIRENGRID_PROTOTYPE_PLAN_SCORE_V1"
    assert score["convention"] == "LOWER_IS_BETTER"
    assert score["weights"] == {
        "eta": 0.35,
        "coverage": 0.40,
        "reserve": 0.20,
        "reposition": 0.05,
        "hospital": 0.00,
    }
    for term in (
        "normalized_eta_term",
        "coverage_penalty",
        "reserve_penalty",
        "reposition_penalty",
        "hospital_penalty",
        "final_score",
    ):
        assert isinstance(score[term], (int, float)), term
    assert score["max_incident_eta_seconds"] == 200.0
    assert score["hospital_penalty"] == 0.0

    # Routes JSON verification
    assert len(data["routes"]) == 2
    for r in data["routes"]:
        assert r["resource_id"] in ["res-amb-01", "res-fire-01"]
        assert r["resource_type"] in ["AMBULANCE", "FIRE_RESCUE"]
        assert r["origin"]["lat"] > 0
        assert r["geometry"]["type"] == "LineString"
        assert len(r["geometry"]["coordinates"]) >= 2
        assert r["distance_m"] > 0
        assert r["eta_seconds"] > 0
        assert r["origin_snap_distance_m"] >= 0
        assert r["destination_snap_distance_m"] >= 0
        assert r["routing_source"] == "OSM_BASE_TRAVEL_TIME"
        # Canonical route records carry responder provenance that the removed
        # Phase 01 planner never recorded.
        assert r["data_reality"] == "SIMULATED"
        assert r["source"]

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
    # The canonical planner audits the whole candidate set, not a single plan.
    assert event.details_json["action"] == "CANDIDATE_SET_GENERATED"
    assert event.details_json["recommended_plan_id"] == data["id"]
    assert data["id"] in event.details_json["candidate_plan_ids"]
    assert event.details_json["incident_version"] == 2
    assert event.details_json["resource_ids_by_plan"][data["id"]] == data["resource_ids"]


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

    configure_canonical_planner(
        monkeypatch,
        planner_graph([("amb-repeat", 30.0600, 31.3400, 120.0)]),
    )

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


def test_legacy_and_candidate_endpoints_share_one_canonical_planner(
    client: TestClient,
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Both planning entry points must resolve to the same canonical engine.

    The legacy endpoint is a facade, so from identical state it must select the
    same responders and produce the same canonical score as the candidate
    endpoint's RECOMMENDED plan.
    """
    responders = [
        ("amb-near", 30.0610, 31.3410, 100.0),
        ("amb-far", 30.0620, 31.3420, 400.0),
    ]
    configure_canonical_planner(monkeypatch, planner_graph(responders))

    legacy_incident = create_test_incident(
        db=db_session,
        required_resources=[{"resource_type": "AMBULANCE", "count": 1}],
    )
    candidate_incident = create_test_incident(
        db=db_session,
        required_resources=[{"resource_type": "AMBULANCE", "count": 1}],
    )
    for resource_id, lat, lon, _travel in responders:
        create_test_resource(
            db=db_session,
            resource_id=resource_id,
            name=resource_id,
            resource_type=ResourceType.AMBULANCE,
            status=ResourceStatus.AVAILABLE,
            lat=lat,
            lon=lon,
        )

    legacy = client.post(f"/api/v1/incidents/{legacy_incident.id}/plans/generate")
    assert legacy.status_code == 201, legacy.text
    legacy_plan = legacy.json()

    candidates = client.post(
        f"/api/v1/incidents/{candidate_incident.id}/plans/generate-candidates"
    )
    assert candidates.status_code == 201, candidates.text
    recommended = [
        plan
        for plan in candidates.json()
        if plan["status"] == ResponsePlanStatus.RECOMMENDED.value
    ]
    assert len(recommended) == 1

    assert legacy_plan["resource_ids"] == recommended[0]["resource_ids"] == ["amb-near"]
    assert (
        legacy_plan["score_breakdown"]["policy_version"]
        == recommended[0]["score_breakdown"]["policy_version"]
        == "SIRENGRID_PROTOTYPE_PLAN_SCORE_V1"
    )
    assert (
        legacy_plan["score_breakdown"]["final_score"]
        == recommended[0]["score_breakdown"]["final_score"]
    )
    # The legacy response stays a single plan even though a set was persisted.
    assert isinstance(legacy_plan, dict)
    assert legacy_plan["status"] == ResponsePlanStatus.RECOMMENDED.value


def test_concurrent_legacy_generation_yields_one_authoritative_candidate_set(
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Concurrent legacy generation must not persist duplicate current plans.

    Before the canonical facade this endpoint held no write lock and derived
    plan_version from a stale read, so racing requests all returned 201 and
    persisted several RECOMMENDED plans with duplicate versions.
    """
    configure_canonical_planner(
        monkeypatch,
        planner_graph(
            [
                ("amb-race-1", 30.0610, 31.3410, 100.0),
                ("amb-race-2", 30.0620, 31.3420, 200.0),
            ]
        ),
    )
    incident = create_test_incident(
        db=db_session,
        required_resources=[{"resource_type": "AMBULANCE", "count": 1}],
    )
    for resource_id, lat, lon in (
        ("amb-race-1", 30.0610, 31.3410),
        ("amb-race-2", 30.0620, 31.3420),
    ):
        create_test_resource(
            db=db_session,
            resource_id=resource_id,
            name=resource_id,
            resource_type=ResourceType.AMBULANCE,
            status=ResourceStatus.AVAILABLE,
            lat=lat,
            lon=lon,
        )

    worker_count = 3
    start_barrier = threading.Barrier(worker_count)

    def generate(_worker: int) -> int:
        with TestClient(app) as worker_client:
            start_barrier.wait(timeout=30.0)
            return worker_client.post(
                f"/api/v1/incidents/{incident.id}/plans/generate"
            ).status_code

    with concurrent.futures.ThreadPoolExecutor(max_workers=worker_count) as executor:
        codes = sorted(
            future.result(timeout=120.0)
            for future in [executor.submit(generate, i) for i in range(worker_count)]
        )

    assert codes.count(201) == 1, codes
    assert codes.count(409) == worker_count - 1, codes
    assert 500 not in codes, codes

    db_session.expire_all()
    plans = db_session.scalars(
        select(ResponsePlan).where(ResponsePlan.incident_id == incident.id)
    ).all()
    recommended = [
        plan for plan in plans if plan.status == ResponsePlanStatus.RECOMMENDED
    ]
    assert len(recommended) == 1
    plan_versions = [plan.plan_version for plan in plans]
    assert len(plan_versions) == len(set(plan_versions)), plan_versions

    reloaded = db_session.get(Incident, incident.id)
    assert reloaded is not None
    assert reloaded.version == 2
    assert reloaded.current_plan_id == recommended[0].id


@pytest.mark.parametrize(
    "status",
    [
        IncidentStatus.CLOSED,
        IncidentStatus.CANCELLED_FALSE_REPORT,
        IncidentStatus.DUPLICATE_MERGED,
        IncidentStatus.REQUIRES_REVIEW,
    ],
)
@pytest.mark.parametrize("endpoint", ["generate", "generate-candidates"])
def test_planning_is_fenced_for_non_actionable_incidents(
    client: TestClient,
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
    status: IncidentStatus,
    endpoint: str,
) -> None:
    """Neither planning entry point may act on a non-actionable incident.

    A merged, cancelled, closed, or review-held incident must not be revived
    into AWAITING_APPROVAL by generating a plan for it.
    """
    configure_canonical_planner(
        monkeypatch,
        planner_graph([("amb-fence", 30.0610, 31.3410, 100.0)]),
    )
    incident = create_test_incident(
        db=db_session,
        status=status,
        required_resources=[{"resource_type": "AMBULANCE", "count": 1}],
    )
    create_test_resource(
        db=db_session,
        resource_id="amb-fence",
        name="Fence Ambulance",
        resource_type=ResourceType.AMBULANCE,
        status=ResourceStatus.AVAILABLE,
        lat=30.0610,
        lon=31.3410,
    )

    response = client.post(f"/api/v1/incidents/{incident.id}/plans/{endpoint}")
    assert response.status_code == 409, response.text
    assert status.value in response.json()["detail"]

    # The incident must not be mutated or revived by the rejected attempt.
    db_session.expire_all()
    reloaded = db_session.get(Incident, incident.id)
    assert reloaded is not None
    assert reloaded.status == status
    assert reloaded.version == 1
    assert reloaded.current_plan_id is None
    assert (
        db_session.scalars(
            select(ResponsePlan).where(ResponsePlan.incident_id == incident.id)
        ).all()
        == []
    )


def test_approval_is_fenced_when_incident_becomes_non_actionable(
    client: TestClient,
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A plan recommended before a merge must not be approvable afterwards.

    Otherwise a duplicate that was merged away could still commit responders.
    """
    configure_canonical_planner(
        monkeypatch,
        planner_graph([("amb-late-merge", 30.0610, 31.3410, 100.0)]),
    )
    incident = create_test_incident(
        db=db_session,
        required_resources=[{"resource_type": "AMBULANCE", "count": 1}],
    )
    resource = create_test_resource(
        db=db_session,
        resource_id="amb-late-merge",
        name="Late Merge Ambulance",
        resource_type=ResourceType.AMBULANCE,
        status=ResourceStatus.AVAILABLE,
        lat=30.0610,
        lon=31.3410,
    )

    generated = client.post(f"/api/v1/incidents/{incident.id}/plans/generate")
    assert generated.status_code == 201, generated.text
    plan = generated.json()

    # The incident is merged into a canonical incident after the plan existed.
    db_session.expire_all()
    reloaded = db_session.get(Incident, incident.id)
    assert reloaded is not None
    reloaded.status = IncidentStatus.DUPLICATE_MERGED
    db_session.commit()

    approval = client.post(
        f"/api/v1/plans/{plan['id']}/approve",
        json={
            "expected_incident_version": plan["incident_version"],
            "expected_plan_version": plan["plan_version"],
            "operator_reference": "dispatcher-fence",
        },
    )
    assert approval.status_code == 409, approval.text
    assert IncidentStatus.DUPLICATE_MERGED.value in approval.json()["detail"]

    # No responder may be committed to the merged incident.
    db_session.expire_all()
    reloaded_resource = db_session.get(EmergencyResource, resource.id)
    assert reloaded_resource is not None
    assert reloaded_resource.status == ResourceStatus.AVAILABLE
    assert reloaded_resource.assigned_incident_id is None


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


def _cancel(client: TestClient, incident_id: str, version: int) -> Any:
    return client.post(
        f"/api/v1/incidents/{incident_id}/cancel",
        json={
            "expected_incident_version": version,
            "operator_reference": "dispatcher-cancel",
            "reason": "Caller confirmed no emergency",
        },
    )


def test_cancel_false_report_before_any_plan(
    client: TestClient,
    db_session: Session,
) -> None:
    """An operator can terminate a freshly created false report."""
    incident = create_test_incident(db=db_session)

    response = _cancel(client, incident.id, 1)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == IncidentStatus.CANCELLED_FALSE_REPORT.value
    assert body["version"] == 2

    db_session.expire_all()
    reloaded = db_session.get(Incident, incident.id)
    assert reloaded is not None
    assert reloaded.status == IncidentStatus.CANCELLED_FALSE_REPORT
    assert reloaded.current_plan_id is None

    events = db_session.scalars(
        select(TimelineEvent).where(
            TimelineEvent.incident_id == incident.id,
            TimelineEvent.event_type == "INCIDENT_CANCELLED",
        )
    ).all()
    assert len(events) == 1
    assert events[0].details_json["from_status"] == (
        IncidentStatus.ACTIVE_UNCONFIRMED.value
    )
    assert events[0].details_json["operator_reference"] == "dispatcher-cancel"


def test_cancel_false_report_supersedes_unapproved_candidate_plans(
    client: TestClient,
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Cancelling before approval must leave no approvable plan behind."""
    configure_canonical_planner(
        monkeypatch,
        planner_graph([("amb-cancel", 30.0610, 31.3410, 100.0)]),
    )
    incident = create_test_incident(
        db=db_session,
        required_resources=[{"resource_type": "AMBULANCE", "count": 1}],
    )
    create_test_resource(
        db=db_session,
        resource_id="amb-cancel",
        name="Cancel Ambulance",
        resource_type=ResourceType.AMBULANCE,
        status=ResourceStatus.AVAILABLE,
        lat=30.0610,
        lon=31.3410,
    )
    generated = client.post(f"/api/v1/incidents/{incident.id}/plans/generate")
    assert generated.status_code == 201, generated.text
    plan = generated.json()

    response = _cancel(client, incident.id, plan["incident_version"])
    assert response.status_code == 200, response.text

    db_session.expire_all()
    plans = db_session.scalars(
        select(ResponsePlan).where(ResponsePlan.incident_id == incident.id)
    ).all()
    assert plans, "the generated candidate set should still exist for audit"
    assert all(item.status == ResponsePlanStatus.SUPERSEDED for item in plans)

    # The superseded recommendation must no longer be approvable.
    approval = client.post(
        f"/api/v1/plans/{plan['id']}/approve",
        json={
            "expected_incident_version": plan["incident_version"] + 1,
            "expected_plan_version": plan["plan_version"],
            "operator_reference": "dispatcher-cancel",
        },
    )
    assert approval.status_code == 409, approval.text

    # And planning may not restart on a cancelled incident.
    replan = client.post(f"/api/v1/incidents/{incident.id}/plans/generate")
    assert replan.status_code == 409, replan.text


def test_cancel_false_report_rejects_stale_version_and_repeat(
    client: TestClient,
    db_session: Session,
) -> None:
    """Stale and repeated cancellation must fail visibly without mutation."""
    incident = create_test_incident(db=db_session)

    stale = _cancel(client, incident.id, 99)
    assert stale.status_code == 409
    assert "version mismatch" in stale.json()["detail"].lower()

    db_session.expire_all()
    unchanged = db_session.get(Incident, incident.id)
    assert unchanged is not None
    assert unchanged.status == IncidentStatus.ACTIVE_UNCONFIRMED
    assert unchanged.version == 1

    assert _cancel(client, incident.id, 1).status_code == 200
    repeat = _cancel(client, incident.id, 2)
    assert repeat.status_code == 409
    assert "INCIDENT_NOT_CANCELLABLE" in repeat.json()["detail"]

    db_session.expire_all()
    final = db_session.get(Incident, incident.id)
    assert final is not None
    assert final.version == 2, "a rejected repeat must not bump the version"


def test_cancel_false_report_rejected_after_response_is_committed(
    client: TestClient,
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A committed response is never silently demobilized by a cancellation."""
    configure_canonical_planner(
        monkeypatch,
        planner_graph([("amb-committed", 30.0610, 31.3410, 100.0)]),
    )
    incident = create_test_incident(
        db=db_session,
        required_resources=[{"resource_type": "AMBULANCE", "count": 1}],
    )
    resource = create_test_resource(
        db=db_session,
        resource_id="amb-committed",
        name="Committed Ambulance",
        resource_type=ResourceType.AMBULANCE,
        status=ResourceStatus.AVAILABLE,
        lat=30.0610,
        lon=31.3410,
    )
    generated = client.post(f"/api/v1/incidents/{incident.id}/plans/generate")
    assert generated.status_code == 201, generated.text
    plan = generated.json()
    approved = client.post(
        f"/api/v1/plans/{plan['id']}/approve",
        json={
            "expected_incident_version": plan["incident_version"],
            "expected_plan_version": plan["plan_version"],
            "operator_reference": "dispatcher-approve",
        },
    )
    assert approved.status_code == 200, approved.text

    db_session.expire_all()
    active = db_session.get(Incident, incident.id)
    assert active is not None
    response = _cancel(client, incident.id, active.version)
    assert response.status_code == 409, response.text
    detail = response.json()["detail"]
    assert "RESPONSE_ALREADY_COMMITTED" in detail
    assert resource.id in detail

    # The responder stays committed and the incident stays operational.
    db_session.expire_all()
    reloaded_resource = db_session.get(EmergencyResource, resource.id)
    assert reloaded_resource is not None
    assert reloaded_resource.status == ResourceStatus.ASSIGNED
    assert reloaded_resource.assigned_incident_id == incident.id
    reloaded_incident = db_session.get(Incident, incident.id)
    assert reloaded_incident is not None
    assert reloaded_incident.status == IncidentStatus.RESPONSE_ACTIVE


def test_concurrent_cancellation_has_exactly_one_winner(
    db_session: Session,
) -> None:
    """Two racing cancellations must serialize into one authoritative result."""
    incident = create_test_incident(db=db_session)

    worker_count = 3
    start_barrier = threading.Barrier(worker_count)

    def cancel(_worker: int) -> int:
        with TestClient(app) as worker_client:
            start_barrier.wait(timeout=30.0)
            return _cancel(worker_client, incident.id, 1).status_code

    with concurrent.futures.ThreadPoolExecutor(max_workers=worker_count) as executor:
        codes = sorted(
            future.result(timeout=60.0)
            for future in [executor.submit(cancel, i) for i in range(worker_count)]
        )

    assert codes.count(200) == 1, codes
    assert codes.count(409) == worker_count - 1, codes
    assert 500 not in codes, codes

    db_session.expire_all()
    reloaded = db_session.get(Incident, incident.id)
    assert reloaded is not None
    assert reloaded.status == IncidentStatus.CANCELLED_FALSE_REPORT
    assert reloaded.version == 2, "exactly one cancellation may bump the version"
    events = db_session.scalars(
        select(TimelineEvent).where(
            TimelineEvent.incident_id == incident.id,
            TimelineEvent.event_type == "INCIDENT_CANCELLED",
        )
    ).all()
    assert len(events) == 1

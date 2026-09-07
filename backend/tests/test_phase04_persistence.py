from __future__ import annotations

from copy import deepcopy
import concurrent.futures
from datetime import datetime, timezone
import threading
import uuid

import networkx as nx
import pytest
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session
from fastapi.testclient import TestClient

import app.planning as planning
from app.candidate_evaluation import evaluate_candidate_combination
from app.candidate_generation import CandidateCombination, CandidateResource, CandidateResponder
from app.candidate_persistence import persist_candidate_set
from app.coverage import CoverageZone
from app.db import init_db
from app.main import app
from app.models import EmergencyResource, Incident, ResponsePlan, TimelineEvent
from app.response_requirements import ResponseRequirement
from app.routing import compute_traffic_aware_route
from app.schemas import (
    ConfidenceLevel,
    Coordinate,
    DataReality,
    IncidentStatus,
    ResourceStatus,
    ResourceType,
    ResponsePlanStatus,
    Severity,
)


@pytest.fixture(autouse=True)
def setup_isolated_db_tables(isolated_engine: Engine) -> None:
    init_db(isolated_engine)


def persistence_graph() -> nx.MultiDiGraph:
    graph = nx.MultiDiGraph()
    for node, lon in (
        ("resource-a", 31.300),
        ("resource-b", 31.301),
        ("zone", 31.302),
    ):
        graph.add_node(node, x=lon, y=30.0)
    graph.add_edge(
        "resource-a",
        "zone",
        key="0",
        length=100.0,
        travel_time=100.0,
        base_travel_time_s=100.0,
    )
    graph.add_edge(
        "resource-b",
        "zone",
        key="0",
        length=200.0,
        travel_time=200.0,
        base_travel_time_s=200.0,
    )
    return graph


def reposition_graph() -> nx.MultiDiGraph:
    graph = nx.MultiDiGraph()
    for node, lon in (
        ("amb-dispatch", 31.300),
        ("fire-dispatch", 31.301),
        ("amb-reserve", 31.302),
        ("fire-reserve", 31.303),
        ("zone-west", 31.304),
        ("zone-target", 31.305),
        ("zone-east", 31.306),
    ):
        graph.add_node(node, x=lon, y=30.0)
    for source, destination, travel_time in (
        ("amb-dispatch", "zone-target", 100.0),
        ("fire-dispatch", "zone-target", 110.0),
        ("fire-reserve", "zone-target", 100.0),
        ("amb-reserve", "zone-west", 600.0),
        ("zone-west", "zone-target", 500.0),
    ):
        graph.add_edge(
            source,
            destination,
            key="0",
            length=travel_time,
            travel_time=travel_time,
            base_travel_time_s=travel_time,
        )
    return graph


def reposition_zones() -> tuple[CoverageZone, ...]:
    def square(min_lon: float, max_lon: float) -> dict[str, object]:
        return {
            "type": "Polygon",
            "coordinates": [[
                [min_lon, 29.9995], [max_lon, 29.9995],
                [max_lon, 30.0005], [min_lon, 30.0005], [min_lon, 29.9995],
            ]],
        }

    return tuple(
        CoverageZone(zone_id, Coordinate(lat=30.0, lon=lon), 100.0, square(low, high))
        for zone_id, lon, low, high in (
            ("zone-west", 31.304, 31.3035, 31.3045),
            ("zone-target", 31.305, 31.3045, 31.3055),
            ("zone-east", 31.306, 31.3055, 31.3065),
        )
    )


def phase04_candidate_resources() -> tuple[CandidateResource, CandidateResource]:
    return tuple(
        CandidateResource(
            resource_id=resource_id,
            resource_type=ResourceType.AMBULANCE,
            capability_tags=(),
            status=ResourceStatus.AVAILABLE,
            assigned_incident_id=None,
            coordinate=Coordinate(lat=30.0, lon=longitude),
            data_reality=DataReality.SIMULATED,
            source="phase03_simulated_resource",
        )
        for resource_id, longitude in (("resource-a", 31.300), ("resource-b", 31.301))
    )  # type: ignore[return-value]


def evaluated_candidates() -> tuple[object, object]:
    graph = persistence_graph()
    zones = (CoverageZone("zone", Coordinate(lat=30.0, lon=31.302), 100.0),)
    requirement = ResponseRequirement(ResourceType.AMBULANCE, 1)
    resources = phase04_candidate_resources()
    candidates = []
    for resource in resources:
        route = compute_traffic_aware_route(
            graph,
            resource.coordinate,
            Coordinate(lat=30.0, lon=31.302),
            None,
        )
        candidates.append(
            evaluate_candidate_combination(
                graph=graph,
                zones=zones,
                resources=resources,
                requirements=(requirement,),
                combination=CandidateCombination(
                    (CandidateResponder(requirement, resource, route),)
                ),
                traffic_snapshot=None,
                modeled_at=datetime(2026, 9, 7, tzinfo=timezone.utc),
            )
        )
    return tuple(candidates)  # type: ignore[return-value]


def persistence_incident(db: Session) -> Incident:
    incident = Incident(
        id=str(uuid.uuid4()),
        version=1,
        incident_type="traffic_collision",
        severity=Severity.LOW,
        confidence_level=ConfidenceLevel.HIGH,
        status=IncidentStatus.ACTIVE_UNCONFIRMED,
        latitude=30.0,
        longitude=31.302,
        required_resources_json=[{"resource_type": "AMBULANCE", "count": 1}],
        provenance_json={"source": "operator_manual_entry", "data_reality": "SIMULATED"},
    )
    db.add(incident)
    db.add_all(
        EmergencyResource(
            id=resource_id,
            version=1,
            name=resource_id,
            resource_type=ResourceType.AMBULANCE,
            status=ResourceStatus.AVAILABLE,
            latitude=30.0,
            longitude=longitude,
            capability_tags_json=[],
            provenance_json={"source": "phase03_simulated_resource", "data_reality": "SIMULATED"},
        )
        for resource_id, longitude in (("resource-a", 31.300), ("resource-b", 31.301))
    )
    db.commit()
    return incident


def configure_candidate_endpoint(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(planning, "load_routing_graph", persistence_graph)
    monkeypatch.setattr(
        planning,
        "load_population_zones",
        lambda _path: (
            CoverageZone(
                zone_id="zone",
                centroid=Coordinate(lat=30.0, lon=31.302),
                population=100.0,
            ),
        ),
    )
    monkeypatch.setattr(
        planning.traffic_runtime,
        "capture_snapshot",
        lambda *_args, **_kwargs: None,
    )


def test_persist_candidate_set_retains_ranked_phase04_facts_and_single_current_recommendation(
    db_session: Session,
) -> None:
    incident = persistence_incident(db_session)
    candidates = evaluated_candidates()

    persisted = persist_candidate_set(
        db_session,
        incident,
        candidates,
        candidate_set_id="candidate-set-persistence",
    )

    assert [plan.status for plan in persisted] == [
        ResponsePlanStatus.RECOMMENDED,
        ResponsePlanStatus.ALTERNATIVE,
    ]
    db_session.expire_all()
    reloaded_incident = db_session.get(Incident, incident.id)
    assert reloaded_incident is not None
    assert reloaded_incident.version == 2
    assert reloaded_incident.current_plan_id == persisted[0].id
    all_plans = db_session.scalars(
        select(ResponsePlan).where(ResponsePlan.incident_id == incident.id)
    ).all()
    assert sum(plan.status == ResponsePlanStatus.RECOMMENDED for plan in all_plans) == 1
    assert all(plan.metrics_json["phase04"]["candidate_set_id"] == "candidate-set-persistence" for plan in all_plans)
    assert all("baseline_joint" in plan.metrics_json["phase04"] for plan in all_plans)
    assert all("post_dispatch_joint" in plan.metrics_json["phase04"] for plan in all_plans)
    assert all(plan.score_breakdown_json["policy_version"] == "SIRENGRID_PROTOTYPE_PLAN_SCORE_V1" for plan in all_plans)
    assert all(plan.metrics_json["phase04"]["population_data_reality"] == "REAL_DERIVED" for plan in all_plans)

    events = db_session.scalars(
        select(TimelineEvent).where(
            TimelineEvent.incident_id == incident.id,
            TimelineEvent.event_type == "PLAN_GENERATED",
        )
    ).all()
    assert len(events) == 1
    assert events[0].details_json["candidate_plan_ids"] == [plan.id for plan in persisted]


def test_persist_one_candidate_keeps_recommended_approval_compatible(
    db_session: Session,
) -> None:
    incident = persistence_incident(db_session)
    candidate = evaluated_candidates()[0]

    persisted = persist_candidate_set(db_session, incident, (candidate,))

    assert len(persisted) == 1
    assert persisted[0].status == ResponsePlanStatus.RECOMMENDED
    assert persisted[0].metrics_json["phase04"]["candidate_count"] == 1
    assert persisted[0].incident_version == incident.version
    assert persisted[0].resource_ids_json == ["resource-a"]


def test_phase04_candidate_generation_endpoint_persists_comparison_set(
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    incident = persistence_incident(db_session)
    monkeypatch.setattr(planning, "load_routing_graph", persistence_graph)
    monkeypatch.setattr(
        planning,
        "load_population_zones",
        lambda _path: (
            CoverageZone(
                zone_id="zone",
                centroid=Coordinate(lat=30.0, lon=31.302),
                population=100.0,
            ),
        ),
    )
    monkeypatch.setattr(
        planning.traffic_runtime,
        "capture_snapshot",
        lambda *_args, **_kwargs: None,
    )

    with TestClient(app) as client:
        response = client.post(
            f"/api/v1/incidents/{incident.id}/plans/generate-candidates"
        )

    assert response.status_code == 201, response.text
    body = response.json()
    assert [plan["status"] for plan in body] == ["RECOMMENDED", "ALTERNATIVE"]
    assert body[0]["candidate_set_id"] == body[1]["candidate_set_id"]
    assert body[0]["metrics"]["phase04"]["joint_aggregation_policy"] == (
        "JOINT_ALL_REQUIRED_COHORTS_V1"
    )
    assert all("reposition_proposal" not in plan["metrics"]["phase04"] for plan in body)
    assert all(plan["score_breakdown"]["reposition_penalty"] == 0.0 for plan in body)


def test_concurrent_candidate_generations_have_one_winner(
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    incident = persistence_incident(db_session)
    configure_candidate_endpoint(monkeypatch)
    barrier = threading.Barrier(2)
    generate = planning.generate_candidate_combinations

    def synchronized_generate(**kwargs: object):
        barrier.wait(timeout=5.0)
        return generate(**kwargs)

    monkeypatch.setattr(planning, "generate_candidate_combinations", synchronized_generate)

    def request_generation() -> tuple[int, dict[str, object] | list[object]]:
        with TestClient(app) as client:
            response = client.post(
                f"/api/v1/incidents/{incident.id}/plans/generate-candidates"
            )
            return response.status_code, response.json()

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _: request_generation(), range(2)))

    assert sorted(code for code, _ in results) == [201, 409]
    assert "stale planning state" in next(
        body["detail"]
        for code, body in results
        if code == 409 and isinstance(body, dict)
    ).lower()
    db_session.expire_all()
    persisted_incident = db_session.get(Incident, incident.id)
    assert persisted_incident is not None
    assert persisted_incident.version == 2
    plans = db_session.scalars(
        select(ResponsePlan).where(ResponsePlan.incident_id == incident.id)
    ).all()
    active = [
        plan
        for plan in plans
        if plan.status in (ResponsePlanStatus.RECOMMENDED, ResponsePlanStatus.ALTERNATIVE)
    ]
    assert len(active) == 2
    assert sum(plan.status == ResponsePlanStatus.RECOMMENDED for plan in plans) == 1
    assert len({plan.metrics_json["phase04"]["candidate_set_id"] for plan in active}) == 1
    assert len(db_session.scalars(
        select(TimelineEvent).where(
            TimelineEvent.incident_id == incident.id,
            TimelineEvent.event_type == "PLAN_GENERATED",
        )
    ).all()) == 1


def test_incident_correction_rejects_stale_candidate_generation(
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    incident = persistence_incident(db_session)
    configure_candidate_endpoint(monkeypatch)
    captured = threading.Event()
    resume = threading.Event()
    generate = planning.generate_candidate_combinations

    def blocked_generate(**kwargs: object):
        captured.set()
        assert resume.wait(timeout=5.0)
        return generate(**kwargs)

    monkeypatch.setattr(planning, "generate_candidate_combinations", blocked_generate)
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(
            lambda: TestClient(app).post(
                f"/api/v1/incidents/{incident.id}/plans/generate-candidates"
            )
        )
        assert captured.wait(timeout=5.0)
        with TestClient(app) as client:
            correction = client.patch(
                f"/api/v1/incidents/{incident.id}/facts",
                json={
                    "expected_incident_version": 1,
                    "operator_reference": "fix-003-concurrency-test",
                    "location": {"lat": 30.001, "lon": 31.303},
                },
            )
        resume.set()
        generation = future.result(timeout=10.0)

    assert correction.status_code == 200, correction.text
    assert generation.status_code == 409, generation.text
    db_session.expire_all()
    persisted_incident = db_session.get(Incident, incident.id)
    assert persisted_incident is not None
    assert persisted_incident.version == 2
    assert (persisted_incident.latitude, persisted_incident.longitude) == (30.001, 31.303)
    assert persisted_incident.current_plan_id is None
    assert db_session.scalars(
        select(ResponsePlan).where(ResponsePlan.incident_id == incident.id)
    ).all() == []


def test_resource_mutation_rejects_stale_candidate_generation(
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    incident = persistence_incident(db_session)
    configure_candidate_endpoint(monkeypatch)
    captured = threading.Event()
    resume = threading.Event()
    generate = planning.generate_candidate_combinations

    def blocked_generate(**kwargs: object):
        captured.set()
        assert resume.wait(timeout=5.0)
        return generate(**kwargs)

    monkeypatch.setattr(planning, "generate_candidate_combinations", blocked_generate)
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(
            lambda: TestClient(app).post(
                f"/api/v1/incidents/{incident.id}/plans/generate-candidates"
            )
        )
        assert captured.wait(timeout=5.0)
        with TestClient(app) as client:
            mutation = client.patch(
                "/api/v1/resources/resource-a/state",
                json={
                    "expected_resource_version": 1,
                    "status": "OUT_OF_SERVICE",
                    "operator_reference": "fix-003-concurrency-test",
                },
            )
        resume.set()
        generation = future.result(timeout=10.0)

    assert mutation.status_code == 200, mutation.text
    assert generation.status_code == 409, generation.text
    db_session.expire_all()
    resource = db_session.get(EmergencyResource, "resource-a")
    persisted_incident = db_session.get(Incident, incident.id)
    assert resource is not None
    assert resource.version == 2
    assert resource.status == ResourceStatus.OUT_OF_SERVICE
    assert persisted_incident is not None
    assert persisted_incident.current_plan_id is None
    assert db_session.scalars(
        select(ResponsePlan).where(ResponsePlan.incident_id == incident.id)
    ).all() == []


def test_phase04_candidate_generation_executes_reposition_before_ranking_and_persistence(
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    graph = reposition_graph()
    incident = Incident(
        id=str(uuid.uuid4()),
        version=1,
        incident_type="traffic_collision",
        severity=Severity.HIGH,
        confidence_level=ConfidenceLevel.HIGH,
        status=IncidentStatus.ACTIVE_UNCONFIRMED,
        latitude=30.0,
        longitude=31.305,
        required_resources_json=[
            {"resource_type": "AMBULANCE", "count": 1},
            {"resource_type": "FIRE_RESCUE", "count": 1},
        ],
        provenance_json={"source": "operator_manual_entry", "data_reality": "SIMULATED"},
    )
    resources = [
        EmergencyResource(
            id=resource_id,
            version=1,
            name=resource_id,
            resource_type=resource_type,
            status=ResourceStatus.AVAILABLE,
            latitude=30.0,
            longitude=longitude,
            capability_tags_json=[],
            provenance_json={"source": "phase03_simulated_resource", "data_reality": "SIMULATED"},
        )
        for resource_id, resource_type, longitude in (
            ("amb-dispatch", ResourceType.AMBULANCE, 31.300),
            ("fire-dispatch", ResourceType.FIRE_RESCUE, 31.301),
            ("amb-reserve", ResourceType.AMBULANCE, 31.302),
            ("fire-reserve", ResourceType.FIRE_RESCUE, 31.303),
        )
    ]
    db_session.add(incident)
    db_session.add_all(resources)
    db_session.commit()
    resource_state = {
        resource.id: (resource.status, resource.assigned_incident_id, resource.latitude, resource.longitude)
        for resource in resources
    }
    graph_state = deepcopy(list(graph.edges(data=True, keys=True)))
    calls = 0
    real_simulate = planning.simulate_repositioning

    def tracked_simulate(**kwargs: object):
        nonlocal calls
        calls += 1
        return real_simulate(**kwargs)

    monkeypatch.setattr(planning, "load_routing_graph", lambda: graph)
    monkeypatch.setattr(planning, "load_population_zones", lambda _path: reposition_zones())
    monkeypatch.setattr(planning.traffic_runtime, "capture_snapshot", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(planning, "simulate_repositioning", tracked_simulate)

    with TestClient(app) as client:
        response = client.post(f"/api/v1/incidents/{incident.id}/plans/generate-candidates")

    assert response.status_code == 201, response.text
    body = response.json()
    assert calls == len(body)
    selected = next(
        plan for plan in body
        if plan["metrics"]["phase04"].get("reposition_proposal")
    )
    proposal = selected["metrics"]["phase04"]["reposition_proposal"]
    score = selected["score_breakdown"]
    assert proposal["target_zone_id"] == "zone-target"
    assert proposal["staging_zone_id"] == "zone-west"
    assert proposal["repositioned_resource_id"] == "amb-reserve"
    assert score["proposed_reposition_eta_seconds"] == proposal["reposition_eta_seconds"] == 600.0
    assert score["reposition_penalty"] == pytest.approx(1.0)
    assert score["weighted_terms"]["reposition"] == pytest.approx(0.05)
    assert score["final_score"] == pytest.approx(sum(score["weighted_terms"].values()))
    assert [plan["candidate_rank"] for plan in body] == list(range(len(body)))
    assert [plan["score_breakdown"]["final_score"] for plan in body] == sorted(
        plan["score_breakdown"]["final_score"] for plan in body
    )
    db_session.expire_all()
    assert {
        resource.id: (resource.status, resource.assigned_incident_id, resource.latitude, resource.longitude)
        for resource in db_session.scalars(select(EmergencyResource)).all()
    } == resource_state
    assert list(graph.edges(data=True, keys=True)) == graph_state

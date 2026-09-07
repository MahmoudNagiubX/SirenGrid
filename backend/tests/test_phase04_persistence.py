from __future__ import annotations

from datetime import datetime, timezone
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

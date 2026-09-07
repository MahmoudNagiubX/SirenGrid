from __future__ import annotations

from datetime import datetime, timezone
import uuid

import networkx as nx
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session
from fastapi.testclient import TestClient

from app.db import init_db
from app.main import app
from app.models import EmergencyResource, Incident, ReplanEvaluation, ResponsePlan
from app.replanning import merge_pending_trigger
from app.candidate_generation import CandidateResource, _is_hard_eligible
from app.candidate_generation import CandidateCombination, CandidateResponder
from app.candidate_evaluation import evaluate_candidate_combination
from app.coverage import CoverageZone
from app.routing import compute_traffic_aware_route
from app.response_requirements import ResponseRequirement
from app.response_requirements import RequirementSource, ResolvedResponseRequirements
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


def test_replan_evaluation_persists_pending_trigger_state(
    isolated_engine: Engine,
    db_session: Session,
) -> None:
    init_db(isolated_engine)
    incident = Incident(
        id=str(uuid.uuid4()),
        version=4,
        incident_type="traffic_collision",
        severity=Severity.HIGH,
        confidence_level=ConfidenceLevel.HIGH,
        status=IncidentStatus.RESPONSE_ACTIVE,
        latitude=30.05,
        longitude=31.34,
        current_plan_id="approved-plan",
    )
    evaluation = ReplanEvaluation(
        id=str(uuid.uuid4()),
        incident_id=incident.id,
        active_plan_id="approved-plan",
        input_fingerprint="a" * 64,
        status="PENDING",
        trigger_reasons_json=["RESOURCE_UNAVAILABLE"],
        input_references_json={"resource_version": 3},
        first_triggered_at=datetime.now(timezone.utc),
        last_triggered_at=datetime.now(timezone.utc),
    )
    db_session.add_all([incident, evaluation])
    db_session.commit()

    saved = db_session.scalar(
        select(ReplanEvaluation).where(ReplanEvaluation.id == evaluation.id)
    )

    assert saved is not None
    assert saved.status == "PENDING"
    assert saved.active_plan_id == "approved-plan"
    assert saved.trigger_reasons_json == ["RESOURCE_UNAVAILABLE"]


def test_pending_trigger_coalescing_unions_reasons_and_keeps_latest_references() -> None:
    merged_reasons, merged_references = merge_pending_trigger(
        existing_reasons=["TRAFFIC_CHANGED"],
        existing_references={"traffic_snapshot_id": "traffic-1", "resource_version": 1},
        new_reasons=["RESOURCE_UNAVAILABLE", "TRAFFIC_CHANGED"],
        new_references={"traffic_snapshot_id": "traffic-2"},
    )

    assert merged_reasons == ["RESOURCE_UNAVAILABLE", "TRAFFIC_CHANGED"]
    assert merged_references == {
        "traffic_snapshot_id": "traffic-2",
        "resource_version": 1,
    }


def test_replan_candidate_filter_allows_only_same_incident_active_resources() -> None:
    requirement = ResponseRequirement(
        resource_type=ResourceType.AMBULANCE,
        minimum_count=1,
    )
    same_incident = CandidateResource(
        resource_id="res-same",
        resource_type=ResourceType.AMBULANCE,
        capability_tags=(),
        status=ResourceStatus.EN_ROUTE,
        assigned_incident_id="incident-1",
        coordinate=Coordinate(lat=30.05, lon=31.34),
        data_reality=DataReality.SIMULATED,
        source="test",
    )
    other_incident = CandidateResource(
        resource_id="res-other",
        resource_type=ResourceType.AMBULANCE,
        capability_tags=(),
        status=ResourceStatus.EN_ROUTE,
        assigned_incident_id="incident-2",
        coordinate=Coordinate(lat=30.05, lon=31.34),
        data_reality=DataReality.SIMULATED,
        source="test",
    )

    assert _is_hard_eligible(same_incident, requirement, incident_id="incident-1")
    assert not _is_hard_eligible(other_incident, requirement, incident_id="incident-1")


def test_trigger_endpoint_coalesces_without_incrementing_incident_version(
    isolated_engine: Engine,
    db_session: Session,
) -> None:
    init_db(isolated_engine)
    incident = Incident(
        id=str(uuid.uuid4()),
        version=4,
        incident_type="traffic_collision",
        severity=Severity.HIGH,
        confidence_level=ConfidenceLevel.HIGH,
        status=IncidentStatus.RESPONSE_ACTIVE,
        latitude=30.05,
        longitude=31.34,
        current_plan_id="approved-plan",
    )
    plan = ResponsePlan(
        id="approved-plan",
        incident_id=incident.id,
        incident_version=4,
        plan_version=1,
        status=ResponsePlanStatus.APPROVED,
        resource_ids_json=[],
        routes_json=[],
        metrics_json={},
        score_breakdown_json={},
    )
    db_session.add_all([incident, plan])
    db_session.commit()

    client = TestClient(app)
    first = client.post(
        f"/api/v1/incidents/{incident.id}/replan/triggers",
        json={
            "expected_incident_version": 4,
            "trigger_reasons": ["TRAFFIC_CHANGED"],
            "input_references": {"traffic_snapshot_id": "traffic-1"},
        },
    )
    second = client.post(
        f"/api/v1/incidents/{incident.id}/replan/triggers",
        json={
            "expected_incident_version": 4,
            "trigger_reasons": ["RESOURCE_UNAVAILABLE"],
            "input_references": {"traffic_snapshot_id": "traffic-2"},
        },
    )

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["status"] == "PENDING"
    assert first.json()["pending_plan_id"] is None
    assert second.json()["id"] == first.json()["id"]
    assert second.json()["trigger_reasons"] == [
        "RESOURCE_UNAVAILABLE",
        "TRAFFIC_CHANGED",
    ]
    assert second.json()["input_references"] == {
        "traffic_snapshot_id": "traffic-2",
    }

    db_session.expire_all()
    saved_incident = db_session.get(Incident, incident.id)
    evaluations = db_session.scalars(
        select(ReplanEvaluation).where(ReplanEvaluation.incident_id == incident.id)
    ).all()
    assert saved_incident is not None
    assert saved_incident.version == 4
    assert saved_incident.current_plan_id == "approved-plan"
    assert len(evaluations) == 1


def test_explicit_flush_records_no_material_change_without_new_plan(
    isolated_engine: Engine,
    db_session: Session,
) -> None:
    init_db(isolated_engine)
    incident = Incident(
        id=str(uuid.uuid4()),
        version=4,
        incident_type="traffic_collision",
        severity=Severity.HIGH,
        confidence_level=ConfidenceLevel.HIGH,
        status=IncidentStatus.RESPONSE_ACTIVE,
        latitude=30.05,
        longitude=31.34,
        current_plan_id="approved-plan",
    )
    plan = ResponsePlan(
        id="approved-plan",
        incident_id=incident.id,
        incident_version=4,
        plan_version=1,
        status=ResponsePlanStatus.APPROVED,
        resource_ids_json=[],
        routes_json=[],
        metrics_json={},
        score_breakdown_json={},
    )
    db_session.add_all([incident, plan])
    db_session.commit()
    client = TestClient(app)

    trigger = client.post(
        f"/api/v1/incidents/{incident.id}/replan/triggers",
        json={
            "expected_incident_version": 4,
            "trigger_reasons": ["TRAFFIC_CHANGED"],
            "input_references": {
                "old_eta_seconds": 400,
                "new_eta_seconds": 401,
                "route_edge_overlap_ratio": 1.0,
            },
        },
    )
    flushed = client.post(
        f"/api/v1/incidents/{incident.id}/replan/evaluate",
        json={"expected_incident_version": 4},
    )

    assert trigger.status_code == 200
    assert flushed.status_code == 200
    body = flushed.json()
    assert body["status"] == "NO_MATERIAL_CHANGE"
    assert body["material"] is False
    assert body["plans"] == []
    assert body["incident_version"] == 4
    assert body["pending_plan_id"] is None


def test_pending_replacement_approval_switches_active_plan_pointer_once(
    isolated_engine: Engine,
    db_session: Session,
) -> None:
    init_db(isolated_engine)
    incident = Incident(
        id=str(uuid.uuid4()),
        version=6,
        incident_type="traffic_collision",
        severity=Severity.HIGH,
        confidence_level=ConfidenceLevel.HIGH,
        status=IncidentStatus.RESPONSE_ACTIVE,
        latitude=30.05,
        longitude=31.34,
        current_plan_id="approved-plan",
        pending_replan_plan_id="replacement-plan",
    )
    active = ResponsePlan(
        id="approved-plan",
        incident_id=incident.id,
        incident_version=5,
        plan_version=1,
        status=ResponsePlanStatus.APPROVED,
        resource_ids_json=[],
        routes_json=[],
        metrics_json={},
        score_breakdown_json={},
    )
    replacement = ResponsePlan(
        id="replacement-plan",
        incident_id=incident.id,
        incident_version=6,
        plan_version=2,
        status=ResponsePlanStatus.RECOMMENDED,
        resource_ids_json=[],
        routes_json=[],
        metrics_json={"replan": {"active_plan_id": active.id}},
        score_breakdown_json={},
    )
    db_session.add_all([incident, active, replacement])
    db_session.commit()
    client = TestClient(app)

    response = client.post(
        "/api/v1/plans/replacement-plan/approve",
        json={
            "expected_incident_version": 6,
            "expected_plan_version": 2,
            "operator_reference": "operator-1",
        },
    )

    assert response.status_code == 200
    db_session.expire_all()
    saved_incident = db_session.get(Incident, incident.id)
    saved_active = db_session.get(ResponsePlan, active.id)
    saved_replacement = db_session.get(ResponsePlan, replacement.id)
    assert saved_incident is not None
    assert saved_active is not None
    assert saved_replacement is not None
    assert saved_incident.version == 7
    assert saved_incident.current_plan_id == replacement.id
    assert saved_incident.pending_replan_plan_id is None
    assert saved_active.status == ResponsePlanStatus.SUPERSEDED
    assert saved_replacement.status == ResponsePlanStatus.APPROVED


def test_material_flush_persists_pending_replacement_without_repointing_active_plan(
    isolated_engine: Engine,
    db_session: Session,
    monkeypatch,
) -> None:
    init_db(isolated_engine)
    incident = Incident(
        id=str(uuid.uuid4()),
        version=4,
        incident_type="traffic_collision",
        severity=Severity.LOW,
        confidence_level=ConfidenceLevel.HIGH,
        status=IncidentStatus.RESPONSE_ACTIVE,
        latitude=30.0,
        longitude=31.302,
        current_plan_id="approved-plan",
        required_resources_json=[{"resource_type": "AMBULANCE", "count": 1}],
    )
    active = ResponsePlan(
        id="approved-plan",
        incident_id=incident.id,
        incident_version=3,
        plan_version=1,
        status=ResponsePlanStatus.APPROVED,
        resource_ids_json=[],
        routes_json=[],
        metrics_json={},
        score_breakdown_json={},
    )
    db_session.add_all([incident, active])
    db_session.commit()

    graph = nx.MultiDiGraph()
    graph.add_node("resource", x=31.3, y=30.0)
    graph.add_node("incident", x=31.302, y=30.0)
    graph.add_edge(
        "resource",
        "incident",
        key="0",
        length=200.0,
        travel_time=20.0,
        base_travel_time_s=20.0,
    )
    requirement = ResponseRequirement(ResourceType.AMBULANCE, 1)
    resource = CandidateResource(
        resource_id="resource-a",
        resource_type=ResourceType.AMBULANCE,
        capability_tags=(),
        status=ResourceStatus.AVAILABLE,
        assigned_incident_id=None,
        coordinate=Coordinate(lat=30.0, lon=31.3),
        data_reality=DataReality.SIMULATED,
        source="phase03_simulated_resource",
    )
    route = compute_traffic_aware_route(
        graph,
        resource.coordinate,
        Coordinate(lat=30.0, lon=31.302),
        None,
    )
    candidate = evaluate_candidate_combination(
        graph=graph,
        zones=(CoverageZone("zone-1", Coordinate(lat=30.0, lon=31.302), 100.0),),
        resources=(resource,),
        requirements=(requirement,),
        combination=CandidateCombination(
            (CandidateResponder(requirement, resource, route),)
        ),
        traffic_snapshot=None,
        modeled_at=datetime(2026, 9, 8, tzinfo=timezone.utc),
    )
    resolution = ResolvedResponseRequirements(
        requirements=(requirement,),
        source=RequirementSource.STRUCTURED_SOURCE,
        matrix_version=None,
        prototype_policy_label=None,
    )
    monkeypatch.setattr(
        "app.replanning.evaluate_phase04_candidate_set",
        lambda *args, **kwargs: (resolution, (candidate,), {}, kwargs["now_utc"]),
    )
    client = TestClient(app)
    trigger = client.post(
        f"/api/v1/incidents/{incident.id}/replan/triggers",
        json={
            "expected_incident_version": 4,
            "trigger_reasons": ["TRAFFIC_CHANGED"],
            "input_references": {
                "old_eta_seconds": 100,
                "new_eta_seconds": 160,
                "route_edge_overlap_ratio": 1.0,
            },
        },
    )
    flushed = client.post(
        f"/api/v1/incidents/{incident.id}/replan/evaluate",
        json={"expected_incident_version": 4},
    )

    assert trigger.status_code == 200
    assert flushed.status_code == 200, flushed.text
    body = flushed.json()
    assert body["status"] == "REPLACEMENT_RECOMMENDED"
    assert body["material"] is True
    assert len(body["plans"]) == 1
    assert body["plans"][0]["status"] == "RECOMMENDED"

    db_session.expire_all()
    saved_incident = db_session.get(Incident, incident.id)
    saved_plan = db_session.get(ResponsePlan, body["plans"][0]["id"])
    assert saved_incident is not None
    assert saved_plan is not None
    assert saved_incident.version == 5
    assert saved_incident.current_plan_id == active.id
    assert saved_incident.pending_replan_plan_id == saved_plan.id
    assert saved_plan.metrics_json["replan"]["old_approved_plan_id"] == active.id

    repeat = client.post(
        f"/api/v1/incidents/{incident.id}/replan/triggers",
        json={
            "expected_incident_version": 5,
            "trigger_reasons": ["TRAFFIC_CHANGED"],
            "input_references": {
                "old_eta_seconds": 100,
                "new_eta_seconds": 160,
                "route_edge_overlap_ratio": 1.0,
            },
        },
    )
    assert repeat.status_code == 200
    assert repeat.json()["idempotent"] is True


def test_phase04_generation_cannot_overwrite_an_active_approved_plan(
    isolated_engine: Engine,
    db_session: Session,
) -> None:
    init_db(isolated_engine)
    incident = Incident(
        id=str(uuid.uuid4()),
        version=4,
        incident_type="traffic_collision",
        severity=Severity.LOW,
        confidence_level=ConfidenceLevel.HIGH,
        status=IncidentStatus.RESPONSE_ACTIVE,
        latitude=30.05,
        longitude=31.34,
        current_plan_id="approved-plan",
        required_resources_json=[{"resource_type": "AMBULANCE", "count": 1}],
    )
    plan = ResponsePlan(
        id="approved-plan",
        incident_id=incident.id,
        incident_version=3,
        plan_version=1,
        status=ResponsePlanStatus.APPROVED,
        resource_ids_json=[],
        routes_json=[],
        metrics_json={},
        score_breakdown_json={},
    )
    db_session.add_all([incident, plan])
    db_session.commit()
    response = TestClient(app).post(
        f"/api/v1/incidents/{incident.id}/plans/generate-candidates"
    )

    assert response.status_code == 409
    db_session.expire_all()
    saved = db_session.get(Incident, incident.id)
    assert saved is not None
    assert saved.current_plan_id == plan.id
    assert saved.pending_replan_plan_id is None


def test_required_assigned_resource_outage_records_replan_trigger(
    isolated_engine: Engine,
    db_session: Session,
) -> None:
    init_db(isolated_engine)
    incident = Incident(
        id=str(uuid.uuid4()),
        version=4,
        incident_type="traffic_collision",
        severity=Severity.LOW,
        confidence_level=ConfidenceLevel.HIGH,
        status=IncidentStatus.RESPONSE_ACTIVE,
        latitude=30.05,
        longitude=31.34,
        current_plan_id="approved-plan",
    )
    plan = ResponsePlan(
        id="approved-plan",
        incident_id=incident.id,
        incident_version=4,
        plan_version=1,
        status=ResponsePlanStatus.APPROVED,
        resource_ids_json=["resource-a"],
        routes_json=[],
        metrics_json={},
        score_breakdown_json={},
    )
    resource = EmergencyResource(
        id="resource-a",
        version=1,
        name="Resource A",
        resource_type=ResourceType.AMBULANCE,
        capability_tags_json=[],
        status=ResourceStatus.ASSIGNED,
        latitude=30.05,
        longitude=31.34,
        assigned_incident_id=incident.id,
        provenance_json={"data_reality": DataReality.SIMULATED.value},
    )
    db_session.add_all([incident, plan, resource])
    db_session.commit()

    response = TestClient(app).patch(
        "/api/v1/resources/resource-a/state",
        json={
            "expected_resource_version": 1,
            "incident_id": incident.id,
            "status": "OUT_OF_SERVICE",
            "operator_reference": "operator-1",
        },
    )

    assert response.status_code == 200, response.text
    db_session.expire_all()
    saved_resource = db_session.get(EmergencyResource, resource.id)
    pending = db_session.scalar(
        select(ReplanEvaluation).where(
            ReplanEvaluation.incident_id == incident.id,
            ReplanEvaluation.status == "PENDING",
        )
    )
    assert saved_resource is not None
    assert saved_resource.status == ResourceStatus.OUT_OF_SERVICE
    assert pending is not None
    assert pending.trigger_reasons_json == ["RESOURCE_UNAVAILABLE"]

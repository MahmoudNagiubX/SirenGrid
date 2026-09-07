from __future__ import annotations

import concurrent.futures
from datetime import datetime, timezone
import threading
from typing import Any

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from app.db import init_db
from app.main import app
from app.models import EmergencyResource, Incident, ResponsePlan, TimelineEvent
from app.schemas import (
    ConfidenceLevel,
    IncidentStatus,
    ResourceStatus,
    ResourceType,
    ResponsePlanStatus,
    Severity,
)


@pytest.fixture(autouse=True)
def setup_isolated_db_tables(isolated_engine: Engine) -> None:
    init_db(isolated_engine)


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def create_incident(db: Session, incident_id: str, version: int = 5) -> Incident:
    now = datetime.now(timezone.utc)
    incident = Incident(
        id=incident_id,
        version=version,
        incident_type="traffic_collision",
        severity=Severity.HIGH,
        confidence_level=ConfidenceLevel.HIGH,
        status=IncidentStatus.AWAITING_APPROVAL,
        latitude=30.0561,
        longitude=31.3452,
        required_resources_json=[{"resource_type": "AMBULANCE", "count": 1}],
        provenance_json={"source": "test_harness", "data_reality": "SIMULATED"},
        created_at=now,
        updated_at=now,
    )
    db.add(incident)
    db.commit()
    return incident


def create_resource(db: Session, resource_id: str) -> EmergencyResource:
    resource = EmergencyResource(
        id=resource_id,
        version=1,
        name=resource_id,
        resource_type=ResourceType.AMBULANCE,
        status=ResourceStatus.AVAILABLE,
        latitude=30.0561,
        longitude=31.3452,
        capability_tags_json=["BLS"],
        provenance_json={"source": "test_harness", "data_reality": "SIMULATED"},
    )
    db.add(resource)
    db.commit()
    return resource


def create_candidate_plan(
    db: Session,
    incident: Incident,
    *,
    plan_id: str,
    plan_version: int,
    status: ResponsePlanStatus,
    candidate_set_id: str,
    candidate_rank: int,
    resource_id: str,
    candidate_count: int = 3,
) -> ResponsePlan:
    plan = ResponsePlan(
        id=plan_id,
        incident_id=incident.id,
        incident_version=incident.version,
        plan_version=plan_version,
        status=status,
        resource_ids_json=[resource_id],
        routes_json=[
            {
                "resource_id": resource_id,
                "distance_m": 1000.0 + candidate_rank,
                "eta_seconds": 100.0 + candidate_rank,
                "routing_source": "OSM_BASE_TRAVEL_TIME",
            }
        ],
        metrics_json={
            "candidate_set_id": candidate_set_id,
            "candidate_rank": candidate_rank,
            "candidate_count": candidate_count,
            "phase04": {
                "candidate_set_id": candidate_set_id,
                "candidate_rank": candidate_rank,
                "candidate_count": candidate_count,
                "coverage_delta": 0.25 - candidate_rank / 100.0,
                "joint_aggregation_policy": "JOINT_ALL_REQUIRED_COHORTS_V1",
                "prototype_policy_label": "SirenGrid prototype demo configuration",
            },
        },
        score_breakdown_json={
            "policy_version": "SIRENGRID_PROTOTYPE_PLAN_SCORE_V1",
            "final_score": float(candidate_rank),
        },
        created_at=datetime.now(timezone.utc),
    )
    db.add(plan)
    db.commit()
    return plan


def seed_candidate_set(
    db: Session,
    *,
    incident_id: str = "inc-selection",
) -> tuple[Incident, tuple[ResponsePlan, ResponsePlan, ResponsePlan], tuple[EmergencyResource, ...]]:
    incident = create_incident(db, incident_id)
    resource_prefix = incident_id.replace("-", "_")
    resources = tuple(
        create_resource(db, f"res-{resource_prefix}-{index}")
        for index in range(1, 4)
    )
    plan_prefix = incident_id.replace("-", "_")
    plans = (
        create_candidate_plan(
            db,
            incident,
            plan_id=f"plan-{plan_prefix}-recommended",
            plan_version=1,
            status=ResponsePlanStatus.RECOMMENDED,
            candidate_set_id="candidate-set-1",
            candidate_rank=0,
            resource_id=resources[0].id,
        ),
        create_candidate_plan(
            db,
            incident,
            plan_id=f"plan-{plan_prefix}-alternative-1",
            plan_version=2,
            status=ResponsePlanStatus.ALTERNATIVE,
            candidate_set_id="candidate-set-1",
            candidate_rank=1,
            resource_id=resources[1].id,
        ),
        create_candidate_plan(
            db,
            incident,
            plan_id=f"plan-{plan_prefix}-alternative-2",
            plan_version=3,
            status=ResponsePlanStatus.ALTERNATIVE,
            candidate_set_id="candidate-set-1",
            candidate_rank=2,
            resource_id=resources[2].id,
        ),
    )
    incident.current_plan_id = plans[0].id
    db.commit()
    return incident, plans, resources


def selection_payload(incident_version: int, plan_version: int) -> dict[str, Any]:
    return {
        "expected_incident_version": incident_version,
        "expected_plan_version": plan_version,
        "operator_reference": "operator-selection-test",
    }


def test_plan_comparison_exposes_one_recommended_alternatives_and_phase04_facts(
    client: TestClient,
    db_session: Session,
) -> None:
    incident, plans, _resources = seed_candidate_set(db_session)

    response = client.get(f"/api/v1/incidents/{incident.id}/plans")

    assert response.status_code == 200
    body = response.json()
    assert [item["status"] for item in body] == [
        "RECOMMENDED",
        "ALTERNATIVE",
        "ALTERNATIVE",
    ]
    assert sum(item["status"] == "RECOMMENDED" for item in body) == 1
    assert body[0]["candidate_set_id"] == "candidate-set-1"
    assert body[0]["candidate_rank"] == 0
    assert body[1]["metrics"]["phase04"]["joint_aggregation_policy"] == (
        "JOINT_ALL_REQUIRED_COHORTS_V1"
    )
    assert plans[0].id == incident.current_plan_id


def test_select_alternative_atomically_promotes_and_supersedes_without_resource_mutation(
    client: TestClient,
    db_session: Session,
) -> None:
    incident, plans, resources = seed_candidate_set(db_session)
    original_resource_versions = {resource.id: resource.version for resource in resources}

    response = client.post(
        f"/api/v1/incidents/{incident.id}/plans/{plans[1].id}/select",
        json=selection_payload(incident.version, plans[1].plan_version),
    )

    assert response.status_code == 200, response.text
    selected = response.json()
    assert selected["id"] == plans[1].id
    assert selected["status"] == "RECOMMENDED"
    db_session.expire_all()
    persisted_incident = db_session.get(Incident, incident.id)
    assert persisted_incident is not None
    assert persisted_incident.version == 6
    assert persisted_incident.current_plan_id == plans[1].id
    assert db_session.get(ResponsePlan, plans[0].id).status == ResponsePlanStatus.SUPERSEDED
    assert db_session.get(ResponsePlan, plans[1].id).status == ResponsePlanStatus.RECOMMENDED
    assert db_session.get(ResponsePlan, plans[1].id).incident_version == 6
    assert db_session.get(ResponsePlan, plans[2].id).status == ResponsePlanStatus.SUPERSEDED

    for resource_id, original_version in original_resource_versions.items():
        persisted_resource = db_session.get(EmergencyResource, resource_id)
        assert persisted_resource is not None
        assert persisted_resource.version == original_version
        assert persisted_resource.status == ResourceStatus.AVAILABLE
        assert persisted_resource.assigned_incident_id is None

    events = db_session.scalars(
        select(TimelineEvent).where(
            TimelineEvent.incident_id == incident.id,
            TimelineEvent.event_type == "PLAN_ALTERNATIVE_SELECTED",
        )
    ).all()
    assert len(events) == 1
    details = events[0].details_json
    assert details["previous_recommended_plan_id"] == plans[0].id
    assert details["selected_plan_id"] == plans[1].id
    assert details["selected_plan_version"] == plans[1].plan_version
    assert details["resulting_incident_version"] == 6
    assert details["operator_reference"] == "operator-selection-test"
    assert set(details["superseded_candidate_ids"]) == {plans[0].id, plans[2].id}


def test_selection_rejects_stale_version_wrong_incident_and_non_alternative_without_mutation(
    client: TestClient,
    db_session: Session,
) -> None:
    incident, plans, resources = seed_candidate_set(db_session)
    other_incident, _other_plans, _other_resources = seed_candidate_set(
        db_session,
        incident_id="inc-other-selection",
    )
    before_version = incident.version

    stale = client.post(
        f"/api/v1/incidents/{incident.id}/plans/{plans[1].id}/select",
        json=selection_payload(before_version - 1, plans[1].plan_version),
    )
    assert stale.status_code == 409

    wrong_incident = client.post(
        f"/api/v1/incidents/{other_incident.id}/plans/{plans[1].id}/select",
        json=selection_payload(before_version, plans[1].plan_version),
    )
    assert wrong_incident.status_code == 409

    non_alternative = client.post(
        f"/api/v1/incidents/{incident.id}/plans/{plans[0].id}/select",
        json=selection_payload(before_version, plans[0].plan_version),
    )
    assert non_alternative.status_code == 409

    db_session.expire_all()
    persisted_incident = db_session.get(Incident, incident.id)
    assert persisted_incident is not None
    assert persisted_incident.version == before_version
    assert persisted_incident.current_plan_id == plans[0].id
    assert db_session.scalars(
        select(TimelineEvent).where(
            TimelineEvent.incident_id == incident.id,
            TimelineEvent.event_type == "PLAN_ALTERNATIVE_SELECTED",
        )
    ).all() == []
    for resource in resources:
        persisted_resource = db_session.get(EmergencyResource, resource.id)
        assert persisted_resource is not None
        assert persisted_resource.status == ResourceStatus.AVAILABLE


def test_competing_alternative_selections_have_one_winner(
    db_session: Session,
) -> None:
    incident, plans, resources = seed_candidate_set(db_session)
    incident_id = incident.id
    incident_version = incident.version
    competing_plans = tuple((plan.id, plan.plan_version) for plan in plans[1:])
    barrier = threading.Barrier(2)

    def perform_selection(plan_id: str, plan_version: int) -> tuple[int, dict[str, Any]]:
        with TestClient(app) as thread_client:
            barrier.wait(timeout=5.0)
            response = thread_client.post(
                f"/api/v1/incidents/{incident_id}/plans/{plan_id}/select",
                json=selection_payload(incident_version, plan_version),
            )
            return response.status_code, response.json()

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        results = list(
                executor.map(
                        lambda item: perform_selection(item[0], item[1]),
                competing_plans,
            )
        )

    assert [result[0] for result in results].count(200) == 1
    assert [result[0] for result in results].count(409) == 1
    db_session.expire_all()
    persisted_incident = db_session.get(Incident, incident.id)
    assert persisted_incident is not None
    assert persisted_incident.version == 6
    plans_after = db_session.scalars(
        select(ResponsePlan).where(ResponsePlan.incident_id == incident.id)
    ).all()
    assert sum(plan.status == ResponsePlanStatus.RECOMMENDED for plan in plans_after) == 1
    assert persisted_incident.current_plan_id in {plans[1].id, plans[2].id}
    assert len(
        db_session.scalars(
            select(TimelineEvent).where(
                TimelineEvent.incident_id == incident.id,
                TimelineEvent.event_type == "PLAN_ALTERNATIVE_SELECTED",
            )
        ).all()
    ) == 1
    for resource in resources:
        persisted_resource = db_session.get(EmergencyResource, resource.id)
        assert persisted_resource is not None
        assert persisted_resource.status == ResourceStatus.AVAILABLE


def test_selected_recommendation_approval_works_and_old_recommendation_cannot_be_approved(
    client: TestClient,
    db_session: Session,
) -> None:
    incident, plans, resources = seed_candidate_set(db_session)

    selected = client.post(
        f"/api/v1/incidents/{incident.id}/plans/{plans[1].id}/select",
        json=selection_payload(incident.version, plans[1].plan_version),
    )
    assert selected.status_code == 200

    old_approval = client.post(
        f"/api/v1/plans/{plans[0].id}/approve",
        json={
            "expected_incident_version": 6,
            "expected_plan_version": plans[0].plan_version,
        },
    )
    assert old_approval.status_code == 409

    new_approval = client.post(
        f"/api/v1/plans/{plans[1].id}/approve",
        json={
            "expected_incident_version": 6,
            "expected_plan_version": plans[1].plan_version,
        },
    )
    assert new_approval.status_code == 200, new_approval.text
    db_session.expire_all()
    persisted_incident = db_session.get(Incident, incident.id)
    assert persisted_incident is not None
    assert persisted_incident.version == 7
    assert db_session.get(ResponsePlan, plans[1].id).status == ResponsePlanStatus.APPROVED
    assert db_session.get(ResponsePlan, plans[0].id).status == ResponsePlanStatus.SUPERSEDED
    selected_resource = db_session.get(EmergencyResource, resources[1].id)
    assert selected_resource is not None
    assert selected_resource.status == ResourceStatus.ASSIGNED
    assert selected_resource.assigned_incident_id == incident.id

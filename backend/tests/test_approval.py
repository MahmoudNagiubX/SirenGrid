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
from app.models import Approval, EmergencyResource, Incident, ResponsePlan, TimelineEvent
from app.routing import RouteResult
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
    """Initialize all model tables on the isolated test engine."""
    init_db(isolated_engine)


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def create_test_incident(
    db: Session,
    incident_id: str | None = None,
    version: int = 2,
    status: IncidentStatus = IncidentStatus.AWAITING_APPROVAL,
    lat: float = 30.0561,
    lon: float = 31.3452,
    required_resources: list[dict[str, Any]] | None = None,
    current_plan_id: str | None = None,
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
        current_plan_id=current_plan_id,
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
    version: int = 1,
) -> EmergencyResource:
    res = EmergencyResource(
        id=resource_id,
        version=version,
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


def create_test_plan(
    db: Session,
    incident_id: str,
    incident_version: int | None = None,
    plan_version: int = 1,
    status: ResponsePlanStatus = ResponsePlanStatus.RECOMMENDED,
    resource_ids: list[str] | None = None,
    routes: list[dict[str, Any]] | None = None,
    metrics: dict[str, Any] | None = None,
    set_as_current: bool = True,
) -> ResponsePlan:
    inc = db.get(Incident, incident_id)
    if incident_version is None:
        incident_version = inc.version if inc is not None else 1

    if resource_ids is None:
        resource_ids = []
    if routes is None:
        routes = [
            {
                "resource_id": r_id,
                "distance_m": 1200.0,
                "eta_seconds": 180.0,
                "routing_source": "OSM_BASE_TRAVEL_TIME",
            }
            for r_id in resource_ids
        ]
    if metrics is None:
        metrics = {
            "max_arrival_eta_seconds": 180.0,
            "mean_arrival_eta_seconds": 180.0,
            "selected_resource_count": len(resource_ids),
            "routing_source": "OSM_BASE_TRAVEL_TIME",
        }

    plan = ResponsePlan(
        id=str(uuid.uuid4()),
        incident_id=incident_id,
        incident_version=incident_version,
        plan_version=plan_version,
        status=status,
        resource_ids_json=resource_ids,
        routes_json=routes,
        metrics_json=metrics,
        score_breakdown_json={
            "algorithm": "MIN_BASE_ROUTE_ETA_WITH_HARD_AVAILABILITY_CONSTRAINTS",
            "coverage_considered": False,
            "traffic_source": "OSM_BASE_TRAVEL_TIME",
        },
    )
    db.add(plan)
    db.commit()
    db.refresh(plan)

    if set_as_current and inc is not None and inc.current_plan_id is None:
        inc.current_plan_id = plan.id
        db.commit()
        db.refresh(inc)

    return plan


def test_approve_plan_success(client: TestClient, db_session: Session) -> None:
    """Valid approval must transactionally update plan, incident, resources, and log auditable events."""
    incident = create_test_incident(db=db_session, version=2, status=IncidentStatus.AWAITING_APPROVAL)
    res1 = create_test_resource(db=db_session, resource_id="res-amb-01", name="Ambulance 01", version=1)
    res2 = create_test_resource(db=db_session, resource_id="res-amb-02", name="Ambulance 02", version=1)

    plan = create_test_plan(
        db=db_session,
        incident_id=incident.id,
        incident_version=2,
        plan_version=1,
        status=ResponsePlanStatus.RECOMMENDED,
        resource_ids=[res1.id, res2.id],
    )
    incident.current_plan_id = plan.id
    db_session.commit()

    payload = {
        "expected_incident_version": 2,
        "expected_plan_version": 1,
        "operator_reference": "dispatcher-senior-01",
    }

    response = client.post(f"/api/v1/plans/{plan.id}/approve", json=payload)
    assert response.status_code == 200, response.text
    data = response.json()

    # Verify response body shape and contents
    assert data["plan_id"] == plan.id
    assert data["id"] == plan.id
    assert data["status"] == "APPROVED"
    assert data["plan_version"] == 1
    assert data["incident_id"] == incident.id
    assert data["incident_status"] == "RESPONSE_ACTIVE"
    assert data["incident"]["version"] == 3
    assert set(data["resource_ids"]) == {res1.id, res2.id}
    assert len(data["resources"]) == 2
    for r in data["resources"]:
        assert r["status"] == "ASSIGNED"
        assert r["assigned_incident_id"] == incident.id
        assert r["version"] == 2
    assert data["approval"]["action"] == "APPROVE_PLAN"
    assert data["approval"]["operator_reference"] == "dispatcher-senior-01"

    # Verify DB state directly
    db_session.expire_all()
    reloaded_plan = db_session.get(ResponsePlan, plan.id)
    assert reloaded_plan is not None
    assert reloaded_plan.status == ResponsePlanStatus.APPROVED
    assert reloaded_plan.plan_version == 1

    reloaded_inc = db_session.get(Incident, incident.id)
    assert reloaded_inc is not None
    assert reloaded_inc.status == IncidentStatus.RESPONSE_ACTIVE
    assert reloaded_inc.version == 3

    reloaded_r1 = db_session.get(EmergencyResource, res1.id)
    assert reloaded_r1 is not None
    assert reloaded_r1.status == ResourceStatus.ASSIGNED
    assert reloaded_r1.assigned_incident_id == incident.id
    assert reloaded_r1.version == 2

    reloaded_r2 = db_session.get(EmergencyResource, res2.id)
    assert reloaded_r2 is not None
    assert reloaded_r2.status == ResourceStatus.ASSIGNED
    assert reloaded_r2.assigned_incident_id == incident.id
    assert reloaded_r2.version == 2

    # Check Approval record
    approvals = db_session.scalars(
        select(Approval).where(Approval.plan_id == plan.id)
    ).all()
    assert len(approvals) == 1
    approval = approvals[0]
    assert approval.incident_id == incident.id
    assert approval.action == "APPROVE_PLAN"
    assert approval.operator_reference == "dispatcher-senior-01"
    assert approval.expected_incident_version == 2
    assert approval.expected_plan_version == 1

    # Check timeline events (PLAN_APPROVED and RESOURCES_ASSIGNED)
    events = db_session.scalars(
        select(TimelineEvent)
        .where(TimelineEvent.incident_id == incident.id)
        .order_by(TimelineEvent.created_at.asc())
    ).all()
    event_types = [e.event_type for e in events]
    assert "PLAN_APPROVED" in event_types
    assert "RESOURCES_ASSIGNED" in event_types

    plan_app_evt = next(e for e in events if e.event_type == "PLAN_APPROVED")
    assert plan_app_evt.details_json["plan_id"] == plan.id
    assert plan_app_evt.details_json["plan_version"] == 1
    assert plan_app_evt.details_json["incident_version"] == 3

    res_ass_evt = next(e for e in events if e.event_type == "RESOURCES_ASSIGNED")
    assert res_ass_evt.details_json["plan_id"] == plan.id
    assert set(res_ass_evt.details_json["resource_ids"]) == {res1.id, res2.id}
    assert res_ass_evt.details_json["resource_count"] == 2


def test_repeated_approval_returns_409_with_code_and_no_duplicate_mutations(
    client: TestClient,
    db_session: Session,
) -> None:
    """Repeated approval on an already approved plan must return HTTP 409 PLAN_ALREADY_APPROVED without mutating state."""
    incident = create_test_incident(db=db_session, version=2, status=IncidentStatus.AWAITING_APPROVAL)
    res = create_test_resource(db=db_session, resource_id="res-rep-01", name="Ambulance Rep")
    plan = create_test_plan(
        db=db_session,
        incident_id=incident.id,
        incident_version=2,
        plan_version=1,
        status=ResponsePlanStatus.RECOMMENDED,
        resource_ids=[res.id],
    )

    payload = {
        "expected_incident_version": 2,
        "expected_plan_version": 1,
        "operator_reference": "dispatcher-repeat",
    }

    # First approval succeeds
    resp1 = client.post(f"/api/v1/plans/{plan.id}/approve", json=payload)
    assert resp1.status_code == 200

    # Capture state after first approval
    db_session.expire_all()
    inc_after_1 = db_session.get(Incident, incident.id)
    assert inc_after_1 is not None
    assert inc_after_1.version == 3
    approvals_count_1 = len(db_session.scalars(select(Approval).where(Approval.plan_id == plan.id)).all())
    events_count_1 = len(db_session.scalars(select(TimelineEvent).where(TimelineEvent.incident_id == incident.id)).all())

    # Second approval attempt must fail with 409 and PLAN_ALREADY_APPROVED
    resp2 = client.post(
        f"/api/v1/plans/{plan.id}/approve",
        json={"expected_incident_version": 3, "expected_plan_version": 1},
    )
    assert resp2.status_code == 409
    assert "PLAN_ALREADY_APPROVED" in resp2.json()["detail"]

    # Verify no state was changed or duplicated
    db_session.expire_all()
    inc_after_2 = db_session.get(Incident, incident.id)
    assert inc_after_2 is not None
    assert inc_after_2.version == 3

    reloaded_res = db_session.get(EmergencyResource, res.id)
    assert reloaded_res is not None
    assert reloaded_res.version == 2

    approvals_count_2 = len(db_session.scalars(select(Approval).where(Approval.plan_id == plan.id)).all())
    assert approvals_count_2 == approvals_count_1

    events_count_2 = len(db_session.scalars(select(TimelineEvent).where(TimelineEvent.incident_id == incident.id)).all())
    assert events_count_2 == events_count_1


def test_stale_expected_incident_version_returns_409_without_mutation(
    client: TestClient,
    db_session: Session,
) -> None:
    """Stale expected incident version must be rejected before mutation."""
    incident = create_test_incident(db=db_session, version=2, status=IncidentStatus.AWAITING_APPROVAL)
    res = create_test_resource(db=db_session, resource_id="res-stale-inc", name="Resource Stale Inc")
    plan = create_test_plan(
        db=db_session,
        incident_id=incident.id,
        incident_version=2,
        plan_version=1,
        status=ResponsePlanStatus.RECOMMENDED,
        resource_ids=[res.id],
    )

    # Provide stale incident version 1 instead of current 2
    payload = {
        "expected_incident_version": 1,
        "expected_plan_version": 1,
        "operator_reference": "dispatcher-stale",
    }
    response = client.post(f"/api/v1/plans/{plan.id}/approve", json=payload)
    assert response.status_code == 409
    assert "incident version" in response.json()["detail"].lower()

    # Verify no mutation
    db_session.expire_all()
    inc = db_session.get(Incident, incident.id)
    assert inc is not None
    assert inc.status == IncidentStatus.AWAITING_APPROVAL
    assert inc.version == 2

    p = db_session.get(ResponsePlan, plan.id)
    assert p is not None
    assert p.status == ResponsePlanStatus.RECOMMENDED

    r = db_session.get(EmergencyResource, res.id)
    assert r is not None
    assert r.status == ResourceStatus.AVAILABLE
    assert r.assigned_incident_id is None
    assert r.version == 1

    approvals = db_session.scalars(select(Approval).where(Approval.plan_id == plan.id)).all()
    assert len(approvals) == 0


def test_stale_expected_plan_version_returns_409_without_mutation(
    client: TestClient,
    db_session: Session,
) -> None:
    """Stale expected plan version must be rejected before mutation."""
    incident = create_test_incident(db=db_session, version=2, status=IncidentStatus.AWAITING_APPROVAL)
    res = create_test_resource(db=db_session, resource_id="res-stale-plan", name="Resource Stale Plan")
    plan = create_test_plan(
        db=db_session,
        incident_id=incident.id,
        incident_version=2,
        plan_version=1,
        status=ResponsePlanStatus.RECOMMENDED,
        resource_ids=[res.id],
    )

    # Provide mismatched plan version 99 instead of current 1
    payload = {
        "expected_incident_version": 2,
        "expected_plan_version": 99,
        "operator_reference": "dispatcher-stale",
    }
    response = client.post(f"/api/v1/plans/{plan.id}/approve", json=payload)
    assert response.status_code == 409
    assert "plan version" in response.json()["detail"].lower()

    # Verify no mutation
    db_session.expire_all()
    p = db_session.get(ResponsePlan, plan.id)
    assert p is not None
    assert p.status == ResponsePlanStatus.RECOMMENDED

    inc = db_session.get(Incident, incident.id)
    assert inc is not None
    assert inc.version == 2

    r = db_session.get(EmergencyResource, res.id)
    assert r is not None
    assert r.status == ResourceStatus.AVAILABLE
    assert r.assigned_incident_id is None


def test_resource_status_conflict_aborts_entire_transaction(
    client: TestClient,
    db_session: Session,
) -> None:
    """If any selected resource becomes unavailable before approval, entire transaction must fail with 409 without partial assignment."""
    incident = create_test_incident(db=db_session, version=2, status=IncidentStatus.AWAITING_APPROVAL)
    res1 = create_test_resource(db=db_session, resource_id="res-avail", name="Available Resource")
    res2 = create_test_resource(
        db=db_session,
        resource_id="res-unavail",
        name="Unavailable Resource",
        status=ResourceStatus.OUT_OF_SERVICE,
    )
    plan = create_test_plan(
        db=db_session,
        incident_id=incident.id,
        incident_version=2,
        plan_version=1,
        status=ResponsePlanStatus.RECOMMENDED,
        resource_ids=[res1.id, res2.id],
    )

    payload = {
        "expected_incident_version": 2,
        "expected_plan_version": 1,
    }
    response = client.post(f"/api/v1/plans/{plan.id}/approve", json=payload)
    assert response.status_code == 409
    assert "not available" in response.json()["detail"].lower()

    # Assert absolute atomicity: res1 must NOT be partially assigned
    db_session.expire_all()
    r1 = db_session.get(EmergencyResource, res1.id)
    assert r1 is not None
    assert r1.status == ResourceStatus.AVAILABLE
    assert r1.assigned_incident_id is None
    assert r1.version == 1

    r2 = db_session.get(EmergencyResource, res2.id)
    assert r2 is not None
    assert r2.status == ResourceStatus.OUT_OF_SERVICE

    p = db_session.get(ResponsePlan, plan.id)
    assert p is not None
    assert p.status == ResponsePlanStatus.RECOMMENDED

    inc = db_session.get(Incident, incident.id)
    assert inc is not None
    assert inc.status == IncidentStatus.AWAITING_APPROVAL
    assert inc.version == 2

    approvals = db_session.scalars(select(Approval).where(Approval.plan_id == plan.id)).all()
    assert len(approvals) == 0


def test_resource_already_assigned_aborts_transaction(
    client: TestClient,
    db_session: Session,
) -> None:
    """If a resource already has an assigned_incident_id, approval must fail with 409."""
    incident = create_test_incident(db=db_session, version=2, status=IncidentStatus.AWAITING_APPROVAL)
    other_inc = create_test_incident(db=db_session, incident_id="other-inc-99", version=1)
    res = create_test_resource(
        db=db_session,
        resource_id="res-already-assigned",
        name="Assigned Resource",
        status=ResourceStatus.AVAILABLE,
        assigned_incident_id=other_inc.id,
    )
    plan = create_test_plan(
        db=db_session,
        incident_id=incident.id,
        incident_version=2,
        plan_version=1,
        status=ResponsePlanStatus.RECOMMENDED,
        resource_ids=[res.id],
    )

    payload = {
        "expected_incident_version": 2,
        "expected_plan_version": 1,
    }
    response = client.post(f"/api/v1/plans/{plan.id}/approve", json=payload)
    assert response.status_code == 409
    assert "already assigned" in response.json()["detail"].lower()

    db_session.expire_all()
    p = db_session.get(ResponsePlan, plan.id)
    assert p is not None
    assert p.status == ResponsePlanStatus.RECOMMENDED


def test_resource_approved_in_one_plan_blocks_subsequent_plan_approval(
    client: TestClient,
    db_session: Session,
) -> None:
    """Once a resource is assigned via plan approval, another plan targeting the same resource cannot be approved."""
    inc1 = create_test_incident(db=db_session, incident_id="inc-first", version=2, status=IncidentStatus.AWAITING_APPROVAL)
    inc2 = create_test_incident(db=db_session, incident_id="inc-second", version=2, status=IncidentStatus.AWAITING_APPROVAL)
    shared_res = create_test_resource(db=db_session, resource_id="res-shared", name="Shared Amb")

    plan1 = create_test_plan(
        db=db_session,
        incident_id=inc1.id,
        plan_version=1,
        resource_ids=[shared_res.id],
    )
    plan2 = create_test_plan(
        db=db_session,
        incident_id=inc2.id,
        plan_version=1,
        resource_ids=[shared_res.id],
    )

    # Approve plan1 -> succeeds
    resp1 = client.post(
        f"/api/v1/plans/{plan1.id}/approve",
        json={"expected_incident_version": 2, "expected_plan_version": 1},
    )
    assert resp1.status_code == 200

    # Attempt to approve plan2 with now-assigned resource -> fails with 409
    resp2 = client.post(
        f"/api/v1/plans/{plan2.id}/approve",
        json={"expected_incident_version": 2, "expected_plan_version": 1},
    )
    assert resp2.status_code == 409

    db_session.expire_all()
    p2 = db_session.get(ResponsePlan, plan2.id)
    assert p2 is not None
    assert p2.status == ResponsePlanStatus.RECOMMENDED


def test_missing_plan_returns_404(client: TestClient) -> None:
    """Approving a nonexistent plan returns 404."""
    random_id = str(uuid.uuid4())
    payload = {
        "expected_incident_version": 1,
        "expected_plan_version": 1,
    }
    response = client.post(f"/api/v1/plans/{random_id}/approve", json=payload)
    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


def test_missing_referenced_incident_returns_404(client: TestClient, db_session: Session) -> None:
    """If referenced incident does not exist, return a clear 404."""
    plan = create_test_plan(
        db=db_session,
        incident_id="nonexistent-incident-id",
        plan_version=1,
        resource_ids=[],
    )
    payload = {
        "expected_incident_version": 1,
        "expected_plan_version": 1,
    }
    response = client.post(f"/api/v1/plans/{plan.id}/approve", json=payload)
    assert response.status_code == 404
    assert "incident" in response.json()["detail"].lower()


def test_incident_status_not_awaiting_approval_returns_409(
    client: TestClient,
    db_session: Session,
) -> None:
    """Incident must be in AWAITING_APPROVAL status to be approved."""
    incident = create_test_incident(
        db=db_session,
        version=1,
        status=IncidentStatus.ACTIVE_UNCONFIRMED,
    )
    res = create_test_resource(db=db_session, resource_id="res-inc-not-awaiting", name="Amb")
    plan = create_test_plan(
        db=db_session,
        incident_id=incident.id,
        plan_version=1,
        resource_ids=[res.id],
    )

    payload = {
        "expected_incident_version": 1,
        "expected_plan_version": 1,
    }
    response = client.post(f"/api/v1/plans/{plan.id}/approve", json=payload)
    assert response.status_code == 409
    assert "awaiting_approval" in response.json()["detail"].lower()


def test_plan_with_duplicate_resource_ids_rejected_with_409(
    client: TestClient,
    db_session: Session,
) -> None:
    """A plan containing duplicate resource IDs must be safely rejected without duplicate assignments."""
    incident = create_test_incident(db=db_session, version=2, status=IncidentStatus.AWAITING_APPROVAL)
    res = create_test_resource(db=db_session, resource_id="res-dup", name="Duplicate Amb")
    plan = create_test_plan(
        db=db_session,
        incident_id=incident.id,
        plan_version=1,
        resource_ids=[res.id, res.id],
    )

    payload = {
        "expected_incident_version": 2,
        "expected_plan_version": 1,
    }
    response = client.post(f"/api/v1/plans/{plan.id}/approve", json=payload)
    assert response.status_code == 409
    assert "duplicate" in response.json()["detail"].lower()

    db_session.expire_all()
    r = db_session.get(EmergencyResource, res.id)
    assert r is not None
    assert r.status == ResourceStatus.AVAILABLE
    assert r.version == 1


def test_nonexistent_resource_in_plan_rejected_with_409(
    client: TestClient,
    db_session: Session,
) -> None:
    """If a resource in plan.resource_ids_json does not exist in DB, reject with 409."""
    incident = create_test_incident(db=db_session, version=2, status=IncidentStatus.AWAITING_APPROVAL)
    plan = create_test_plan(
        db=db_session,
        incident_id=incident.id,
        plan_version=1,
        resource_ids=["nonexistent-resource-id"],
    )

    payload = {
        "expected_incident_version": 2,
        "expected_plan_version": 1,
    }
    response = client.post(f"/api/v1/plans/{plan.id}/approve", json=payload)
    assert response.status_code == 409
    assert "not found" in response.json()["detail"].lower()


def test_full_generate_then_approve_flow(
    client: TestClient,
    db_session: Session,
) -> None:
    """Integrated flow: generate candidate plan from incident, then execute transactional approval."""
    # 1. Create incident at version 1
    incident = create_test_incident(
        db=db_session,
        version=1,
        status=IncidentStatus.ACTIVE_UNCONFIRMED,
        lat=30.0561,
        lon=31.3452,
        required_resources=[{"resource_type": "AMBULANCE", "count": 1}],
    )
    # 2. Create available ambulance
    res = create_test_resource(
        db=db_session,
        resource_id="res-amb-flow",
        name="Flow Ambulance",
        resource_type=ResourceType.AMBULANCE,
        status=ResourceStatus.AVAILABLE,
        lat=30.0570,
        lon=31.3460,
        version=1,
    )

    # 3. Generate plan
    gen_resp = client.post(f"/api/v1/incidents/{incident.id}/plans/generate")
    assert gen_resp.status_code == 201, gen_resp.text
    gen_data = gen_resp.json()
    plan_id = gen_data["id"]
    assert gen_data["status"] == "RECOMMENDED"
    assert gen_data["plan_version"] == 1
    assert gen_data["incident_version"] == 2
    assert gen_data["resource_ids"] == [res.id]

    # Verify incident transitioned to AWAITING_APPROVAL and version incremented to 2
    db_session.expire_all()
    inc_mid = db_session.get(Incident, incident.id)
    assert inc_mid is not None
    assert inc_mid.status == IncidentStatus.AWAITING_APPROVAL
    assert inc_mid.version == 2

    # 4. Approve plan with expected incident version 2 and expected plan version 1
    appr_resp = client.post(
        f"/api/v1/plans/{plan_id}/approve",
        json={
            "expected_incident_version": gen_data["incident_version"],
            "expected_plan_version": gen_data["plan_version"],
            "operator_reference": "dispatcher-flow",
        },
    )
    assert appr_resp.status_code == 200, appr_resp.text
    appr_data = appr_resp.json()
    assert appr_data["status"] == "APPROVED"
    assert appr_data["incident_status"] == "RESPONSE_ACTIVE"
    assert appr_data["incident"]["version"] == 3
    assert appr_data["resources"][0]["status"] == "ASSIGNED"
    assert appr_data["resources"][0]["assigned_incident_id"] == incident.id
    assert appr_data["resources"][0]["version"] == 2

    # 5. Repeated approval is blocked
    repeat_resp = client.post(
        f"/api/v1/plans/{plan_id}/approve",
        json={
            "expected_incident_version": 3,
            "expected_plan_version": 1,
        },
    )
    assert repeat_resp.status_code == 409
    assert "PLAN_ALREADY_APPROVED" in repeat_resp.json()["detail"]


def test_approval_rejects_superseded_plan_even_with_current_incident_version(
    client: TestClient,
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Regression: generate Plan v1, generate Plan v2, then attempt to approve Plan v1

    using the current incident version; assert HTTP 409 and zero resource, Approval,
    PLAN_APPROVED, and RESOURCES_ASSIGNED mutations.
    """
    incident = create_test_incident(
        db=db_session,
        version=1,
        status=IncidentStatus.ACTIVE_UNCONFIRMED,
        lat=30.0561,
        lon=31.3452,
        required_resources=[{"resource_type": "AMBULANCE", "count": 1}],
    )
    res = create_test_resource(
        db=db_session,
        resource_id="res-amb-reg",
        name="Reg Ambulance",
        resource_type=ResourceType.AMBULANCE,
        status=ResourceStatus.AVAILABLE,
        lat=30.0570,
        lon=31.3460,
        version=1,
    )

    def mock_compute(graph: Any, origin: Any, destination: Any) -> RouteResult:
        return RouteResult(
            nodes=[101, 102],
            geometry={"type": "LineString", "coordinates": [[31.3460, 30.0570], [31.3452, 30.0561]]},
            distance_m=1000.0,
            eta_seconds=120.0,
            origin_snap_distance_m=5.0,
            destination_snap_distance_m=5.0,
            routing_source="OSM_BASE_TRAVEL_TIME",
        )

    monkeypatch.setattr("app.planning.load_routing_graph", lambda: None)
    monkeypatch.setattr("app.planning.compute_route_on_graph", mock_compute)

    # 1. Generate Plan v1
    resp1 = client.post(f"/api/v1/incidents/{incident.id}/plans/generate")
    assert resp1.status_code == 201, resp1.text
    plan1 = resp1.json()
    assert plan1["plan_version"] == 1
    assert plan1["incident_version"] == 2

    # 2. Generate Plan v2
    resp2 = client.post(f"/api/v1/incidents/{incident.id}/plans/generate")
    assert resp2.status_code == 201, resp2.text
    plan2 = resp2.json()
    assert plan2["plan_version"] == 2
    assert plan2["incident_version"] == 3
    assert plan2["id"] != plan1["id"]

    db_session.expire_all()
    inc_current = db_session.get(Incident, incident.id)
    assert inc_current is not None
    assert inc_current.version == 3
    assert inc_current.current_plan_id == plan2["id"]

    # 3. Attempt to approve Plan v1 using current incident version (3) and plan1's plan_version (1)
    appr_resp = client.post(
        f"/api/v1/plans/{plan1['id']}/approve",
        json={
            "expected_incident_version": 3,
            "expected_plan_version": 1,
            "operator_reference": "dispatcher-reg",
        },
    )
    assert appr_resp.status_code == 409

    # 4. Assert zero resource, Approval, PLAN_APPROVED, and RESOURCES_ASSIGNED mutations
    db_session.expire_all()
    reloaded_res = db_session.get(EmergencyResource, res.id)
    assert reloaded_res is not None
    assert reloaded_res.status == ResourceStatus.AVAILABLE
    assert reloaded_res.assigned_incident_id is None
    assert reloaded_res.version == 1

    approvals = db_session.scalars(select(Approval)).all()
    assert len(approvals) == 0

    plan_approved_events = db_session.scalars(
        select(TimelineEvent).where(TimelineEvent.event_type == "PLAN_APPROVED")
    ).all()
    assert len(plan_approved_events) == 0

    resources_assigned_events = db_session.scalars(
        select(TimelineEvent).where(TimelineEvent.event_type == "RESOURCES_ASSIGNED")
    ).all()
    assert len(resources_assigned_events) == 0

    # Incident remains AWAITING_APPROVAL with version 3 and current_plan_id pointing to plan2
    reloaded_inc = db_session.get(Incident, incident.id)
    assert reloaded_inc is not None
    assert reloaded_inc.status == IncidentStatus.AWAITING_APPROVAL
    assert reloaded_inc.version == 3
    assert reloaded_inc.current_plan_id == plan2["id"]


def test_approval_rejects_when_plan_not_current_plan_for_incident(
    client: TestClient,
    db_session: Session,
) -> None:
    """Approval must reject with 409 if incident.current_plan_id != plan.id."""
    incident = create_test_incident(db=db_session, version=2, status=IncidentStatus.AWAITING_APPROVAL)
    res = create_test_resource(db=db_session, resource_id="res-not-curr", name="Amb")
    plan = create_test_plan(
        db=db_session,
        incident_id=incident.id,
        incident_version=2,
        plan_version=1,
        status=ResponsePlanStatus.RECOMMENDED,
        resource_ids=[res.id],
        set_as_current=False,
    )
    incident.current_plan_id = "some-other-plan-id"
    db_session.commit()

    resp = client.post(
        f"/api/v1/plans/{plan.id}/approve",
        json={
            "expected_incident_version": 2,
            "expected_plan_version": 1,
        },
    )
    assert resp.status_code == 409
    assert "current plan" in resp.json()["detail"].lower()


def test_approval_rejects_when_plan_incident_version_mismatch(
    client: TestClient,
    db_session: Session,
) -> None:
    """Approval must reject with 409 if plan.incident_version != incident.version."""
    incident = create_test_incident(db=db_session, version=3, status=IncidentStatus.AWAITING_APPROVAL)
    res = create_test_resource(db=db_session, resource_id="res-ver-mismatch", name="Amb")
    plan = create_test_plan(
        db=db_session,
        incident_id=incident.id,
        incident_version=2,  # mismatch with incident.version (3)
        plan_version=1,
        status=ResponsePlanStatus.RECOMMENDED,
        resource_ids=[res.id],
    )
    incident.current_plan_id = plan.id
    db_session.commit()

    resp = client.post(
        f"/api/v1/plans/{plan.id}/approve",
        json={
            "expected_incident_version": 3,
            "expected_plan_version": 1,
        },
    )
    assert resp.status_code == 409
    assert "incident version" in resp.json()["detail"].lower()

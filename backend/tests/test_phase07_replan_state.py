from __future__ import annotations

from datetime import datetime, timezone
import uuid

from sqlalchemy import Engine, select
from sqlalchemy.orm import Session
from fastapi.testclient import TestClient

from app.db import init_db
from app.main import app
from app.models import Incident, ReplanEvaluation, ResponsePlan
from app.replanning import merge_pending_trigger
from app.schemas import (
    ConfidenceLevel,
    IncidentStatus,
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

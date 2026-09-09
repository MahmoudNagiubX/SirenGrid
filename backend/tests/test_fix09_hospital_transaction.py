from __future__ import annotations

from datetime import datetime, timezone
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from app.db import init_db
from app.hospital_api import load_static_hospitals
from app.main import app
from app.models import (
    HospitalDestination,
    HospitalPreAlert,
    Incident,
    ReplanEvaluation,
    ResponsePlan,
    TimelineEvent,
)
from app.schemas import (
    ConfidenceLevel,
    DataReality,
    HospitalPreAlertStatus,
    IncidentStatus,
    ResponsePlanStatus,
    Severity,
)


def _seed_selected_hospital(
    db: Session,
    *,
    resource_ids: list[str] | None = None,
) -> tuple[Incident, ResponsePlan, HospitalDestination, HospitalPreAlert]:
    hospitals = load_static_hospitals()
    incident = Incident(
        id=str(uuid.uuid4()),
        version=4,
        incident_type="traffic_collision",
        severity=Severity.HIGH,
        confidence_level=ConfidenceLevel.HIGH,
        status=IncidentStatus.RESPONSE_ACTIVE,
        latitude=30.0561,
        longitude=31.3452,
        current_plan_id="approved-hospital-plan",
        transport_required=True,
    )
    plan = ResponsePlan(
        id="approved-hospital-plan",
        incident_id=incident.id,
        incident_version=incident.version,
        plan_version=1,
        status=ResponsePlanStatus.APPROVED,
        resource_ids_json=resource_ids or [],
        routes_json=[],
        metrics_json={},
        score_breakdown_json={},
    )
    destination = HospitalDestination(
        id="selected-hospital-destination",
        incident_id=incident.id,
        plan_id=plan.id,
        option_set_id="hospital-option-set",
        hospital_id=hospitals[0].id,
        status="SELECTED",
        incident_version=incident.version,
        plan_version=plan.plan_version,
        selected_at=datetime.now(timezone.utc),
        provenance_json={"source": "test", "data_reality": DataReality.SIMULATED.value},
    )
    pre_alert = HospitalPreAlert(
        id="prior-hospital-pre-alert",
        incident_id=incident.id,
        plan_id=plan.id,
        destination_id=destination.id,
        status=HospitalPreAlertStatus.SENT.value,
        payload_json={"hospital_id": destination.hospital_id},
        requested_at=datetime.now(timezone.utc),
        data_reality=DataReality.SIMULATED,
        provenance_json={"source": "test-pre-alert"},
    )
    db.add_all([incident, plan, destination, pre_alert])
    db.commit()
    return incident, plan, destination, pre_alert


def _trigger_payload(*, hospital_id: str, expected_version: int = 4) -> dict[str, object]:
    return {
        "expected_incident_version": expected_version,
        "trigger_reasons": ["HOSPITAL_STATE_CHANGED"],
        "input_references": {
            "hospital_id": hospital_id,
            "hospital_unreachable": True,
        },
    }


def test_hospital_unreachable_commits_trigger_and_invalidation_together(
    isolated_engine: Engine,
    db_session: Session,
) -> None:
    init_db(isolated_engine)
    incident, _, destination, pre_alert = _seed_selected_hospital(db_session)

    response = TestClient(app).post(
        f"/api/v1/incidents/{incident.id}/replan/triggers",
        json=_trigger_payload(hospital_id=destination.hospital_id),
    )

    assert response.status_code == 200, response.text
    db_session.expire_all()
    saved_destination = db_session.get(HospitalDestination, destination.id)
    saved_pre_alert = db_session.get(HospitalPreAlert, pre_alert.id)
    evaluation = db_session.scalar(
        select(ReplanEvaluation).where(ReplanEvaluation.incident_id == incident.id)
    )
    event_types = db_session.scalars(
        select(TimelineEvent.event_type).where(TimelineEvent.incident_id == incident.id)
    ).all()

    assert saved_destination is not None
    assert saved_destination.status == "INVALIDATED"
    assert saved_pre_alert is not None
    assert saved_pre_alert.status == HospitalPreAlertStatus.SENT.value
    assert evaluation is not None
    assert event_types.count("REPLAN_TRIGGER_RECORDED") == 1
    assert event_types.count("HOSPITAL_DESTINATION_INVALIDATED") == 1


def test_wrong_hospital_reference_is_rejected_before_trigger_mutation(
    isolated_engine: Engine,
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    init_db(isolated_engine)
    incident, _, destination, _ = _seed_selected_hospital(db_session)
    wrong_hospital_id = load_static_hospitals()[1].id
    published: list[dict[str, object]] = []
    monkeypatch.setattr(
        "app.replanning.publish_operations_event",
        lambda **event: published.append(event),
    )

    response = TestClient(app).post(
        f"/api/v1/incidents/{incident.id}/replan/triggers",
        json=_trigger_payload(hospital_id=wrong_hospital_id),
    )

    assert response.status_code == 409, response.text
    db_session.expire_all()
    saved_incident = db_session.get(Incident, incident.id)
    saved_destination = db_session.get(HospitalDestination, destination.id)

    assert saved_incident is not None
    assert saved_incident.version == 4
    assert saved_destination is not None
    assert saved_destination.status == "SELECTED"
    assert db_session.scalar(
        select(ReplanEvaluation).where(ReplanEvaluation.incident_id == incident.id)
    ) is None
    assert db_session.scalar(
        select(TimelineEvent).where(TimelineEvent.incident_id == incident.id)
    ) is None
    assert published == []


def test_option_generation_failure_rolls_back_hospital_unreachable_command(
    isolated_engine: Engine,
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    init_db(isolated_engine)
    incident, _, destination, pre_alert = _seed_selected_hospital(
        db_session,
        resource_ids=["assigned-resource"],
    )

    def fail_option_generation(*args: object, **kwargs: object) -> None:
        del args, kwargs
        raise RuntimeError("injected hospital option failure")

    published: list[dict[str, object]] = []
    monkeypatch.setattr(
        "app.replanning.publish_operations_event",
        lambda **event: published.append(event),
    )
    monkeypatch.setattr("app.hospital_api._generate_hospital_options", fail_option_generation)
    response_client = TestClient(app, raise_server_exceptions=False)
    response = response_client.post(
        f"/api/v1/incidents/{incident.id}/replan/triggers",
        json=_trigger_payload(hospital_id=destination.hospital_id),
    )

    assert response.status_code == 500
    db_session.expire_all()
    saved_incident = db_session.get(Incident, incident.id)
    saved_destination = db_session.get(HospitalDestination, destination.id)
    saved_pre_alert = db_session.get(HospitalPreAlert, pre_alert.id)

    assert saved_incident is not None
    assert saved_incident.version == 4
    assert saved_destination is not None
    assert saved_destination.status == "SELECTED"
    assert saved_pre_alert is not None
    assert saved_pre_alert.status == HospitalPreAlertStatus.SENT.value
    assert db_session.scalar(
        select(ReplanEvaluation).where(ReplanEvaluation.incident_id == incident.id)
    ) is None
    assert db_session.scalar(
        select(TimelineEvent).where(TimelineEvent.incident_id == incident.id)
    ) is None
    assert published == []


def test_repeated_hospital_unreachable_command_remains_idempotent(
    isolated_engine: Engine,
    db_session: Session,
) -> None:
    init_db(isolated_engine)
    incident, _, destination, _ = _seed_selected_hospital(db_session)
    client = TestClient(app)
    path = f"/api/v1/incidents/{incident.id}/replan/triggers"
    payload = _trigger_payload(hospital_id=destination.hospital_id)

    first = client.post(path, json=payload)
    second = client.post(path, json=payload)

    assert first.status_code == 200, first.text
    assert second.status_code == 200, second.text
    assert second.json()["idempotent"] is True
    db_session.expire_all()
    assert len(db_session.scalars(
        select(ReplanEvaluation).where(ReplanEvaluation.incident_id == incident.id)
    ).all()) == 1
    assert len(db_session.scalars(
        select(TimelineEvent).where(
            TimelineEvent.incident_id == incident.id,
            TimelineEvent.event_type == "HOSPITAL_DESTINATION_INVALIDATED",
        )
    ).all()) == 1

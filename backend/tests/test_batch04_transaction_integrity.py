from __future__ import annotations

from datetime import datetime, timezone
import uuid

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

import app.models as _models  # noqa: F401
from app.db import init_db
from app.main import app
from app.models import (
    EmergencyResource,
    Incident,
    ReplanEvaluation,
    Report,
    ResponsePlan,
    TimelineEvent,
)
from app.schemas import (
    ConfidenceLevel,
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


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def _create_claim_resolution_fixture(db_session: Session) -> Incident:
    incident = Incident(
        id=str(uuid.uuid4()),
        version=4,
        incident_type="traffic_collision",
        severity=Severity.HIGH,
        confidence_level=ConfidenceLevel.HIGH,
        status=IncidentStatus.RESPONSE_ACTIVE,
        latitude=30.0561,
        longitude=31.3452,
        required_hospital_capabilities_json=[],
        required_resources_json=[{"resource_type": "AMBULANCE", "count": 1}],
        current_plan_id="approved-claim-plan",
        provenance_json={"source": "transaction-integrity-test"},
    )
    plan = ResponsePlan(
        id="approved-claim-plan",
        incident_id=incident.id,
        incident_version=4,
        plan_version=1,
        status=ResponsePlanStatus.APPROVED,
        resource_ids_json=[],
        routes_json=[],
        metrics_json={},
        score_breakdown_json={},
    )
    report = Report(
        id="claim-transaction-report",
        incident_id=incident.id,
        source_type="control_room_text",
        source_reference="transaction-claim-source",
        raw_text="The caller reports two casualties.",
        received_at=datetime.now(timezone.utc),
        data_reality=DataReality.SIMULATED,
        provenance_json={"source": "transaction-integrity-test"},
        processing_status="PROCESSED",
        evidence_items_json=[
            {
                "type": "EVIDENCE_CLAIMS",
                "claims": [
                    {
                        "field_name": "required_hospital_capabilities",
                        "value": ["TRAUMA"],
                        "fact_state": "ASSERTED",
                        "evidence_id": "claim-evidence-1",
                        "report_id": "claim-transaction-report",
                        "support_level": "HIGH",
                        "provider": "manual",
                        "model": None,
                        "observed_at": datetime.now(timezone.utc).isoformat(),
                        "provenance": {"source": "transaction-integrity-test"},
                        "uncertainty": None,
                        "provider_confidence": None,
                    }
                ],
            }
        ],
        created_at=datetime.now(timezone.utc),
    )
    db_session.add_all([incident, plan, report])
    db_session.commit()
    return incident


def _resolve_claim_payload(incident: Incident) -> dict[str, object]:
    return {
        "expected_incident_version": incident.version,
        "operator_reference": "transaction-integrity-operator",
        "field_name": "required_hospital_capabilities",
        "value": ["TRAUMA"],
        "selected_evidence_id": "claim-evidence-1",
    }


def test_claim_resolution_success_commits_fact_resolution_and_trigger_once(
    client: TestClient,
    db_session: Session,
) -> None:
    incident = _create_claim_resolution_fixture(db_session)

    resolved = client.post(
        f"/api/v1/incidents/{incident.id}/fact-claims/resolve",
        json=_resolve_claim_payload(incident),
    )

    assert resolved.status_code == 200, resolved.text
    db_session.expire_all()
    saved = db_session.get(Incident, incident.id)
    assert saved is not None
    assert saved.version == 5
    assert saved.required_hospital_capabilities_json == ["TRAUMA"]
    assert saved.provenance_json["resolved_fact_states"] == {
        "required_hospital_capabilities": "CONSISTENT"
    }
    assert saved.provenance_json["resolved_claim_evidence_ids"] == {
        "required_hospital_capabilities": "claim-evidence-1"
    }
    events = db_session.scalars(
        select(TimelineEvent).where(TimelineEvent.incident_id == incident.id)
    ).all()
    assert {event.event_type for event in events} == {
        "FACTS_CORRECTED",
        "REPLAN_TRIGGER_RECORDED",
        "FACT_CLAIM_RESOLVED",
    }
    evaluation = db_session.scalar(
        select(ReplanEvaluation).where(ReplanEvaluation.incident_id == incident.id)
    )
    assert evaluation is not None
    assert evaluation.trigger_reasons_json == ["INCIDENT_FACT_CHANGED"]


def test_claim_resolution_failure_rolls_back_fact_resolution_trigger_and_publication(
    client: TestClient,
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    incident = _create_claim_resolution_fixture(db_session)
    publications: list[dict[str, object]] = []

    def fail_timeline(*args: object, **kwargs: object) -> TimelineEvent:
        del args, kwargs
        raise RuntimeError("controlled claim-resolution timeline failure")

    monkeypatch.setattr("app.phase06_api._timeline_event", fail_timeline)
    monkeypatch.setattr(
        "app.phase06_api.publish_operations_event",
        lambda **kwargs: publications.append(kwargs),
    )

    with pytest.raises(RuntimeError, match="controlled claim-resolution timeline failure"):
        client.post(
            f"/api/v1/incidents/{incident.id}/fact-claims/resolve",
            json=_resolve_claim_payload(incident),
        )

    db_session.expire_all()
    saved = db_session.get(Incident, incident.id)
    assert saved is not None
    assert saved.version == 4
    assert saved.required_hospital_capabilities_json == []
    assert saved.provenance_json == {"source": "transaction-integrity-test"}
    assert db_session.scalars(
        select(TimelineEvent).where(TimelineEvent.incident_id == incident.id)
    ).all() == []
    assert db_session.scalar(
        select(ReplanEvaluation).where(ReplanEvaluation.incident_id == incident.id)
    ) is None
    assert publications == []


def _create_assigned_outage_fixture(
    db_session: Session,
) -> tuple[Incident, EmergencyResource]:
    incident = Incident(
        id=str(uuid.uuid4()),
        version=4,
        incident_type="traffic_collision",
        severity=Severity.HIGH,
        confidence_level=ConfidenceLevel.HIGH,
        status=IncidentStatus.RESPONSE_ACTIVE,
        latitude=30.0561,
        longitude=31.3452,
        current_plan_id="approved-outage-plan",
        provenance_json={"source": "transaction-integrity-test"},
    )
    plan = ResponsePlan(
        id="approved-outage-plan",
        incident_id=incident.id,
        incident_version=4,
        plan_version=1,
        status=ResponsePlanStatus.APPROVED,
        resource_ids_json=["assigned-outage-resource"],
        routes_json=[],
        metrics_json={},
        score_breakdown_json={},
    )
    resource = EmergencyResource(
        id="assigned-outage-resource",
        version=1,
        name="Assigned Outage Resource",
        resource_type=ResourceType.AMBULANCE,
        capability_tags_json=[],
        status=ResourceStatus.ASSIGNED,
        latitude=30.0561,
        longitude=31.3452,
        assigned_incident_id=incident.id,
        provenance_json={"source": "transaction-integrity-test"},
    )
    db_session.add_all([incident, plan, resource])
    db_session.commit()
    return incident, resource


def test_assigned_outage_failure_rolls_back_resource_trigger_timeline_and_publication(
    client: TestClient,
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    incident, resource = _create_assigned_outage_fixture(db_session)
    publications: list[dict[str, object]] = []

    def fail_trigger(*args: object, **kwargs: object) -> None:
        del args, kwargs
        raise RuntimeError("controlled outage-trigger failure")

    monkeypatch.setattr("app.replanning.apply_replan_trigger", fail_trigger)
    monkeypatch.setattr("app.replanning.record_replan_trigger", fail_trigger)
    monkeypatch.setattr(
        "app.resources.publish_operations_event",
        lambda **kwargs: publications.append(kwargs),
    )

    with pytest.raises(RuntimeError, match="controlled outage-trigger failure"):
        client.patch(
            f"/api/v1/resources/{resource.id}/state",
            json={
                "expected_resource_version": resource.version,
                "incident_id": incident.id,
                "status": ResourceStatus.OUT_OF_SERVICE.value,
                "operator_reference": "transaction-integrity-operator",
            },
        )

    db_session.expire_all()
    saved_resource = db_session.get(EmergencyResource, resource.id)
    saved_incident = db_session.get(Incident, incident.id)
    assert saved_resource is not None
    assert saved_incident is not None
    assert saved_resource.status == ResourceStatus.ASSIGNED
    assert saved_resource.version == 1
    assert saved_incident.version == 4
    assert db_session.scalars(
        select(TimelineEvent).where(TimelineEvent.incident_id == incident.id)
    ).all() == []
    assert db_session.scalar(
        select(ReplanEvaluation).where(ReplanEvaluation.incident_id == incident.id)
    ) is None
    assert publications == []

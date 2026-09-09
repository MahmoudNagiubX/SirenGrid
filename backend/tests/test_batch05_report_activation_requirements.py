from __future__ import annotations

from typing import Any

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

import app.models as _models  # noqa: F401 - register all ORM models
from app.db import init_db
from app.main import app
from app.models import Incident, Report, TimelineEvent


@pytest.fixture(autouse=True)
def setup_isolated_db_tables(isolated_engine: Engine) -> None:
    init_db(isolated_engine)


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def _standalone_report_payload() -> dict[str, Any]:
    return {
        "source_type": "control_room_text",
        "source_reference": "caller-batch05",
        "raw_text": "Caller reports a collision near Tayaran Street.",
        "location_text": "Tayaran Street",
        "evidence_items": [
            {
                "type": "operator_entry",
                "uri_or_reference": "call-log-batch05",
                "extracted_facts": {"reported_casualties": 2},
                "provenance": {"source": "control_room", "data_reality": "SIMULATED"},
            }
        ],
    }


def _activation_payload() -> dict[str, Any]:
    return {
        "incident_type": "traffic_collision",
        "severity": "HIGH",
        "confidence_level": "HIGH",
        "location": {"lat": 30.0561, "lon": 31.3452},
        "location_text": "Tayaran Street",
        "required_resources": [{"resource_type": "AMBULANCE", "count": 1}],
        "operator_reference": "activation-operator",
    }


def _create_incident_with_report(
    client: TestClient,
    *,
    required_resources: list[dict[str, Any]] | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    incident_response = client.post(
        "/api/v1/intake/manual",
        json={
            **_activation_payload(),
            "required_resources": required_resources
            or [{"resource_type": "FIRE_RESCUE", "count": 1}],
        },
    )
    assert incident_response.status_code == 201, incident_response.text
    incident = incident_response.json()

    report_response = client.post(
        "/api/v1/reports",
        json={
            "incident_id": incident["id"],
            "source_type": "control_room_text",
            "source_reference": "claim-source-batch05",
            "raw_text": "Operator source identifies ambulance service need.",
        },
    )
    assert report_response.status_code == 201, report_response.text
    report = report_response.json()

    # Keep a stable evidence ID so resolution can prove the selected claim.
    claim_response = client.post(
        f"/api/v1/reports/{report['id']}/claims",
        json={
            "provider": "deterministic-test-provider",
            "model": "fixture",
            "evidence_id": "required-services-evidence",
            "claims": [
                {
                    "field_name": "required_services",
                    "value": ["ambulance"],
                    "fact_state": "ASSERTED",
                    "support_level": "HIGH",
                }
            ],
        },
    )
    assert claim_response.status_code == 200, claim_response.text
    return incident, report


def _required_services_resolution(
    incident_id: str,
    *,
    required_resources: list[dict[str, Any]] | None = None,
    expected_version: int = 1,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "expected_incident_version": expected_version,
        "operator_reference": "requirements-operator",
        "field_name": "required_services",
        "value": ["ambulance"],
        "selected_evidence_id": "required-services-evidence",
    }
    if required_resources is not None:
        payload["required_resources"] = required_resources
    return payload


def test_standalone_report_requires_explicit_operator_activation_command(
    client: TestClient,
    db_session: Session,
) -> None:
    report_response = client.post("/api/v1/reports", json=_standalone_report_payload())
    assert report_response.status_code == 201, report_response.text
    report = report_response.json()
    assert report["incident_id"] is None

    activation = client.post(
        f"/api/v1/reports/{report['id']}/create-incident",
        json=_activation_payload(),
    )

    assert activation.status_code == 201, activation.text
    incident = activation.json()
    assert incident["status"] == "ACTIVE_UNCONFIRMED"
    assert incident["current_plan_id"] is None
    assert db_session.query(Incident).count() == 1

    associated = db_session.get(Report, report["id"])
    assert associated is not None
    assert associated.incident_id == incident["id"]
    assert associated.raw_text == _standalone_report_payload()["raw_text"]
    assert associated.evidence_items_json[0]["extracted_facts"] == {"reported_casualties": 2}


def test_report_activation_requires_operator_reference(
    client: TestClient,
    db_session: Session,
) -> None:
    report_response = client.post("/api/v1/reports", json=_standalone_report_payload())
    report_id = report_response.json()["id"]
    missing_operator = {key: value for key, value in _activation_payload().items() if key != "operator_reference"}

    activation = client.post(
        f"/api/v1/reports/{report_id}/create-incident",
        json=missing_operator,
    )

    assert activation.status_code == 422, activation.text
    assert db_session.query(Incident).count() == 0
    assert db_session.get(Report, report_id).incident_id is None


def test_report_activation_does_not_invent_absent_facts(
    client: TestClient,
    db_session: Session,
) -> None:
    report_response = client.post(
        "/api/v1/reports",
        json={
            "source_type": "control_room_text",
            "source_reference": "unknown-facts-batch05",
            "raw_text": "A possible emergency was reported.",
        },
    )
    assert report_response.status_code == 201

    activation = client.post(
        f"/api/v1/reports/{report_response.json()['id']}/create-incident",
        json=_activation_payload(),
    )
    assert activation.status_code == 201, activation.text
    incident = activation.json()
    assert incident["casualty_count"] is None
    assert incident["trapped_person"] is None
    assert incident["road_blockage"] is None
    assert db_session.get(Incident, incident["id"]) is not None


def test_report_activation_is_idempotent_and_does_not_create_second_incident(
    client: TestClient,
    db_session: Session,
) -> None:
    report_response = client.post("/api/v1/reports", json=_standalone_report_payload())
    report_id = report_response.json()["id"]
    first = client.post(
        f"/api/v1/reports/{report_id}/create-incident",
        json=_activation_payload(),
    )
    assert first.status_code == 201, first.text

    repeated = client.post(
        f"/api/v1/reports/{report_id}/create-incident",
        json=_activation_payload(),
    )
    assert repeated.status_code == 409, repeated.text
    assert db_session.query(Incident).count() == 1


def test_report_activation_rolls_back_incident_and_association_on_required_step_failure(
    monkeypatch: pytest.MonkeyPatch,
    db_session: Session,
) -> None:
    report_client = TestClient(app)
    report_response = report_client.post("/api/v1/reports", json=_standalone_report_payload())
    report_id = report_response.json()["id"]

    def fail_timeline(*_: Any, **__: Any) -> TimelineEvent:
        raise RuntimeError("injected activation timeline failure")

    published: list[dict[str, Any]] = []
    monkeypatch.setattr(
        "app.phase06_api.publish_operations_event",
        lambda **kwargs: published.append(kwargs),
    )
    monkeypatch.setattr("app.phase06_api._timeline_event", fail_timeline)
    client = TestClient(app, raise_server_exceptions=False)
    failed = client.post(
        f"/api/v1/reports/{report_id}/create-incident",
        json=_activation_payload(),
    )

    assert failed.status_code == 500
    db_session.expire_all()
    assert db_session.query(Incident).count() == 0
    report = db_session.get(Report, report_id)
    assert report is not None
    assert report.incident_id is None
    assert db_session.query(TimelineEvent).count() == 0
    assert published == []


def test_required_services_claim_reaches_review_without_changing_authoritative_requirements(
    client: TestClient,
    db_session: Session,
) -> None:
    incident, _ = _create_incident_with_report(client)

    current = db_session.get(Incident, incident["id"])
    assert current is not None
    assert current.required_resources_json == [{"resource_type": "FIRE_RESCUE", "count": 1}]
    assert current.version == 1


def test_required_services_claim_can_be_explicitly_resolved_to_canonical_requirements(
    client: TestClient,
    db_session: Session,
) -> None:
    incident, _ = _create_incident_with_report(client)
    explicit = [
        {
            "resource_type": "AMBULANCE",
            "count": 2,
            "required_capability_tags": ["advanced_life_support"],
        }
    ]

    resolved = client.post(
        f"/api/v1/incidents/{incident['id']}/fact-claims/resolve",
        json=_required_services_resolution(
            incident["id"],
            required_resources=explicit,
        ),
    )

    assert resolved.status_code == 200, resolved.text
    body = resolved.json()["incident"]
    assert body["version"] == 2
    assert body["required_resources"] == explicit
    assert body["provenance"]["resolved_fact_states"]["required_services"] == "CONSISTENT"
    assert body["provenance"]["resolved_claim_evidence_ids"]["required_services"] == (
        "required-services-evidence"
    )

    events = db_session.scalars(
        select(TimelineEvent).where(TimelineEvent.incident_id == incident["id"])
    ).all()
    assert any(event.event_type == "FACT_CLAIM_RESOLVED" for event in events)


def test_required_services_resolution_requires_explicit_operator_count(
    client: TestClient,
    db_session: Session,
) -> None:
    incident, _ = _create_incident_with_report(client)

    response = client.post(
        f"/api/v1/incidents/{incident['id']}/fact-claims/resolve",
        json=_required_services_resolution(incident["id"]),
    )

    assert response.status_code == 422, response.text
    current = db_session.get(Incident, incident["id"])
    assert current is not None
    assert current.version == 1
    assert current.required_resources_json == [{"resource_type": "FIRE_RESCUE", "count": 1}]


def test_ambiguous_required_service_does_not_project_to_authoritative_requirements(
    client: TestClient,
    db_session: Session,
) -> None:
    incident, report = _create_incident_with_report(client)
    replacement_claim = client.post(
        f"/api/v1/reports/{report['id']}/claims",
        json={
            "provider": "deterministic-test-provider",
            "model": "fixture",
            "evidence_id": "ambiguous-service-evidence",
            "claims": [
                {
                    "field_name": "required_services",
                    "value": ["medical emergency"],
                    "fact_state": "ASSERTED",
                    "support_level": "HIGH",
                }
            ],
        },
    )
    assert replacement_claim.status_code == 200, replacement_claim.text

    response = client.post(
        f"/api/v1/incidents/{incident['id']}/fact-claims/resolve",
        json={
            **_required_services_resolution(
                incident["id"],
                required_resources=[{"resource_type": "AMBULANCE", "count": 1}],
            ),
            "value": ["medical emergency"],
            "selected_evidence_id": "ambiguous-service-evidence",
        },
    )

    assert response.status_code == 422, response.text
    current = db_session.get(Incident, incident["id"])
    assert current is not None
    assert current.version == 1
    assert current.required_resources_json == [{"resource_type": "FIRE_RESCUE", "count": 1}]


def test_required_services_resolution_rolls_back_on_timeline_failure(
    monkeypatch: pytest.MonkeyPatch,
    db_session: Session,
) -> None:
    setup_client = TestClient(app)
    incident, _ = _create_incident_with_report(setup_client)

    def fail_timeline(*_: Any, **__: Any) -> TimelineEvent:
        raise RuntimeError("injected claim resolution timeline failure")

    monkeypatch.setattr("app.phase06_api._timeline_event", fail_timeline)
    client = TestClient(app, raise_server_exceptions=False)
    response = client.post(
        f"/api/v1/incidents/{incident['id']}/fact-claims/resolve",
        json=_required_services_resolution(
            incident["id"],
            required_resources=[{"resource_type": "AMBULANCE", "count": 1}],
        ),
    )

    assert response.status_code == 500
    db_session.expire_all()
    current = db_session.get(Incident, incident["id"])
    assert current is not None
    assert current.version == 1
    assert current.required_resources_json == [{"resource_type": "FIRE_RESCUE", "count": 1}]
    assert "required_services" not in (current.provenance_json or {}).get("resolved_fact_states", {})


def test_misspelled_capability_field_remains_rejected_during_service_resolution(
    client: TestClient,
    db_session: Session,
) -> None:
    incident, _ = _create_incident_with_report(client)
    response = client.post(
        f"/api/v1/incidents/{incident['id']}/fact-claims/resolve",
        json=_required_services_resolution(
            incident["id"],
            required_resources=[
                {
                    "resource_type": "AMBULANCE",
                    "count": 1,
                    "required_capabilty_tags": ["advanced_life_support"],
                }
            ],
        ),
    )

    assert response.status_code == 422, response.text
    current = db_session.get(Incident, incident["id"])
    assert current is not None
    assert current.version == 1

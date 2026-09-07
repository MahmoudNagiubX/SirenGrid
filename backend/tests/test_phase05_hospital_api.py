from __future__ import annotations

from typing import Any
import uuid

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import Engine
from sqlalchemy.orm import Session

import app.models as _models  # noqa: F401
from app.db import init_db
from app.main import app
from app.models import EmergencyResource, Incident, ResponsePlan
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


def _create_approved_transport_plan(db: Session) -> tuple[Incident, EmergencyResource, ResponsePlan]:
    incident = Incident(
        id=str(uuid.uuid4()),
        version=4,
        incident_type="traffic_collision",
        severity=Severity.HIGH,
        confidence_level=ConfidenceLevel.HIGH,
        status=IncidentStatus.RESPONSE_ACTIVE,
        latitude=30.0561,
        longitude=31.3452,
        casualty_count=2,
        transport_required=True,
        required_hospital_capabilities_json=[],
        required_resources_json=[{"resource_type": "AMBULANCE", "count": 1}],
        provenance_json={"source": "test_harness", "data_reality": DataReality.SIMULATED.value},
    )
    resource = EmergencyResource(
        id="phase05-amb-01",
        version=2,
        name="Phase 05 Ambulance",
        resource_type=ResourceType.AMBULANCE,
        capability_tags_json=["BLS"],
        status=ResourceStatus.ASSIGNED,
        latitude=30.0600,
        longitude=31.3400,
        assigned_incident_id=incident.id,
        provenance_json={"source": "test_harness"},
    )
    plan = ResponsePlan(
        id=str(uuid.uuid4()),
        incident_id=incident.id,
        incident_version=incident.version,
        plan_version=1,
        status=ResponsePlanStatus.APPROVED,
        resource_ids_json=[resource.id],
        routes_json=[
            {
                "resource_id": resource.id,
                "resource_type": "AMBULANCE",
                "origin": {"lat": resource.latitude, "lon": resource.longitude},
                "route_geometry": {
                    "type": "LineString",
                    "coordinates": [[31.3400, 30.0500], [31.3450, 30.0550], [31.3500, 30.0600]],
                },
                "geometry": {
                    "type": "LineString",
                    "coordinates": [[31.3400, 30.0500], [31.3450, 30.0550], [31.3500, 30.0600]],
                },
                "distance_m": 1200.0,
                "eta_seconds": 180.0,
            }
        ],
        metrics_json={"max_arrival_eta_seconds": 180.0},
        score_breakdown_json={},
    )
    incident.current_plan_id = plan.id
    db.add_all([incident, resource, plan])
    db.commit()
    db.refresh(incident)
    return incident, resource, plan


class _FakeRoute:
    def model_dump(self, mode: str = "python") -> dict[str, Any]:
        del mode
        return {
            "base_nodes": [1, 2],
            "nodes": [1, 2],
            "edge_keys": ["edge-1"],
            "geometry": {
                "type": "LineString",
                "coordinates": [[31.34, 30.06], [31.345, 30.056]],
            },
            "distance_m": 1200.0,
            "eta_seconds": 180.0,
            "base_eta": 180.0,
            "effective_eta": 180.0,
            "traffic_selected_path_base_eta": 180.0,
            "origin_snap_distance_m": 10.0,
            "destination_snap_distance_m": 10.0,
            "routing_source": "OSM_BASE_TRAVEL_TIME",
            "traffic_snapshot_id": None,
            "traffic_snapshot_version": None,
            "traffic_freshness_status": None,
            "matched_traversed_edge_count": 0,
            "total_traversed_edge_count": 1,
            "traffic_coverage_ratio": 0.0,
            "traffic_weight_affected_path_selection": False,
            "traffic_closure_affected_path_selection": False,
            "traffic_fallback_reason": "NO_TOMTOM_SNAPSHOT",
            "alternatives": [],
        }


def test_hospital_api_exposes_all_27_real_static_registry_features(client: TestClient) -> None:
    response = client.get("/api/v1/hospitals")

    assert response.status_code == 200, response.text
    hospitals = response.json()
    assert len(hospitals) == 27
    assert all(item["static_provenance"]["data_reality"] == "REAL_PUBLIC" for item in hospitals)
    assert all(item["static_capacity"] is None for item in hospitals)
    assert all(item["operational_freshness_status"] == "UNKNOWN" for item in hospitals)


def test_hospital_options_require_explicit_transport_and_preserve_unknown_state(
    client: TestClient,
    db_session: Session,
) -> None:
    incident, _, _ = _create_approved_transport_plan(db_session)
    incident.transport_required = None
    db_session.commit()

    response = client.post(f"/api/v1/incidents/{incident.id}/hospital-options")

    assert response.status_code == 409
    assert "UNKNOWN" in response.json()["detail"]


def test_real_hospital_options_path_ranks_and_persists_static_options(
    client: TestClient,
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    incident, resource, plan = _create_approved_transport_plan(db_session)
    monkeypatch.setattr("app.hospital_api.load_routing_graph", lambda: object())
    monkeypatch.setattr("app.hospital_api._traffic_snapshot", lambda graph: None)
    monkeypatch.setattr("app.hospital_api.compute_traffic_aware_route", lambda *args, **kwargs: _FakeRoute())

    response = client.post(f"/api/v1/incidents/{incident.id}/hospital-options")

    assert response.status_code == 200, response.text
    data = response.json()
    assert data["plan_id"] == plan.id
    assert len(data["options"]) == 27
    assert data["options"][0]["score_breakdown"]["policy_version"] == (
        "SIRENGRID_PROTOTYPE_HOSPITAL_SCORE_V1"
    )
    assert data["options"][0]["hospital"]["static_capacity"] is None
    db_session.expire_all()
    persisted = db_session.query(ResponsePlan).filter_by(id=plan.id).one()
    assert persisted.resource_ids_json == [resource.id]


def _generate_options(
    client: TestClient,
    incident: Incident,
    monkeypatch: pytest.MonkeyPatch,
) -> dict[str, Any]:
    monkeypatch.setattr("app.hospital_api.load_routing_graph", lambda: object())
    monkeypatch.setattr("app.hospital_api._traffic_snapshot", lambda graph: None)
    monkeypatch.setattr("app.hospital_api.compute_traffic_aware_route", lambda *args, **kwargs: _FakeRoute())
    response = client.post(f"/api/v1/incidents/{incident.id}/hospital-options")
    assert response.status_code == 200, response.text
    return response.json()


def test_destination_selection_is_version_safe_and_prealert_is_simulated_idempotent(
    client: TestClient,
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    incident, resource, _ = _create_approved_transport_plan(db_session)
    options = _generate_options(client, incident, monkeypatch)
    first_hospital_id = options["options"][0]["hospital"]["id"]

    selected = client.post(
        f"/api/v1/incidents/{incident.id}/hospital-destination/select",
        json={
            "expected_incident_version": 4,
            "expected_plan_version": 1,
            "expected_option_set_version": 1,
            "hospital_id": first_hospital_id,
            "operator_reference": "operator-05",
        },
    )
    assert selected.status_code == 200, selected.text
    destination = selected.json()
    assert destination["hospital_id"] == first_hospital_id

    alert_request = {
        "expected_incident_version": 5,
        "expected_plan_version": 1,
        "operator_reference": "operator-05",
    }
    alert = client.post(f"/api/v1/incidents/{incident.id}/hospital-prealert", json=alert_request)
    assert alert.status_code == 200, alert.text
    alert_data = alert.json()
    assert alert_data["status"] == "ACKNOWLEDGED"
    assert alert_data["data_reality"] == "SIMULATED"
    assert "diagnosis" not in alert_data["payload"]
    assert "patient_count" in alert_data["payload"]
    assert alert_data["payload"]["incoming_resources"] == [resource.id]

    repeated = client.post(f"/api/v1/incidents/{incident.id}/hospital-prealert", json=alert_request)
    assert repeated.status_code == 200
    assert repeated.json()["id"] == alert_data["id"]
    assert client.get(f"/api/v1/incidents/{incident.id}/hospital-prealert").json()["id"] == alert_data["id"]
    assert client.get(f"/api/v1/incidents/{incident.id}/hospital-destination").json()["id"] == destination["id"]

    db_session.expire_all()
    persisted_resource = db_session.get(EmergencyResource, resource.id)
    assert persisted_resource is not None
    assert persisted_resource.status is ResourceStatus.ASSIGNED
    assert persisted_resource.assigned_incident_id == incident.id
    assert persisted_resource.latitude == 30.0600


def test_destination_replacement_before_prealert_rebinds_option_set_and_increments_once(
    client: TestClient,
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    incident, _, _ = _create_approved_transport_plan(db_session)
    options = _generate_options(client, incident, monkeypatch)
    first_id = options["options"][0]["hospital"]["id"]
    second_id = options["options"][1]["hospital"]["id"]

    first = client.post(
        f"/api/v1/incidents/{incident.id}/hospital-destination/select",
        json={
            "expected_incident_version": 4,
            "expected_plan_version": 1,
            "expected_option_set_version": 1,
            "hospital_id": first_id,
            "operator_reference": "operator-05",
        },
    )
    assert first.status_code == 200, first.text
    replacement = client.post(
        f"/api/v1/incidents/{incident.id}/hospital-destination/select",
        json={
            "expected_incident_version": 5,
            "expected_plan_version": 1,
            "expected_option_set_version": 1,
            "hospital_id": second_id,
            "operator_reference": "operator-05",
        },
    )
    assert replacement.status_code == 200, replacement.text
    assert replacement.json()["hospital_id"] == second_id
    db_session.expire_all()
    current_incident = db_session.get(Incident, incident.id)
    assert current_incident is not None
    assert current_incident.version == 6


def test_hospital_simulation_state_uses_unknown_defaults_and_versioned_updates(
    client: TestClient,
) -> None:
    hospital_id = client.get("/api/v1/hospitals").json()[0]["id"]
    first = client.patch(
        f"/api/v1/hospitals/{hospital_id}/simulation-state",
        json={
            "accepting_state": "ACCEPTING",
            "simulated_load_ratio": 0.25,
            "operator_reference": "fixture-05",
        },
    )
    assert first.status_code == 200, first.text
    assert first.json()["accepting_state"] == "ACCEPTING"
    second = client.patch(
        f"/api/v1/hospitals/{hospital_id}/simulation-state",
        json={
            "expected_version": 1,
            "accepting_state": "NOT_ACCEPTING",
            "operator_reference": "fixture-05",
        },
    )
    assert second.status_code == 200, second.text
    assert second.json()["accepting_state"] == "NOT_ACCEPTING"
    stale = client.patch(
        f"/api/v1/hospitals/{hospital_id}/simulation-state",
        json={
            "expected_version": 1,
            "accepting_state": "ACCEPTING",
            "operator_reference": "fixture-05",
        },
    )
    assert stale.status_code == 409

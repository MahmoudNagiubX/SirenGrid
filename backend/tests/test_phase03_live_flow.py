from __future__ import annotations

from typing import Any

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from app.db import init_db
from app.main import app
from app.seed import seed_resources
from app.websocket import reset_operations_stream


@pytest.fixture(autouse=True)
def setup_isolated_db_tables(isolated_engine: Engine) -> None:
    init_db(isolated_engine)


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def _manual_incident_payload() -> dict[str, Any]:
    return {
        "incident_type": "traffic_collision",
        "severity": "HIGH",
        "confidence_level": "HIGH",
        "location": {"lat": 30.0561, "lon": 31.3452},
        "location_text": "Nasr City Phase 03 live-state smoke",
        "casualty_count": 1,
        "required_resources": [
            {"resource_type": "AMBULANCE", "count": 1},
        ],
        "operator_reference": "phase03-live-operator",
    }


def test_phase03_rest_websocket_movement_flow_keeps_rest_canonical(
    client: TestClient,
    db_session: Session,
) -> None:
    """The live stream invalidates while REST preserves canonical incident/resource state."""
    seed_resources(db=db_session)
    reset_operations_stream()

    with client.websocket_connect("/api/v1/ws/operations") as websocket:
        create_response = client.post(
            "/api/v1/intake/manual",
            json=_manual_incident_payload(),
        )
        assert create_response.status_code == 201, create_response.text
        incident = create_response.json()
        incident_id = incident["id"]

        created_event = websocket.receive_json()
        assert created_event["event"] == "incident.created"
        assert created_event["incident_id"] == incident_id
        assert created_event["version"] == 1
        assert created_event["payload"]["version"] == incident["version"]

        plan_response = client.post(f"/api/v1/incidents/{incident_id}/plans/generate")
        assert plan_response.status_code == 201, plan_response.text
        plan = plan_response.json()

        plan_event = websocket.receive_json()
        assert plan_event["event"] == "incident.updated"
        assert plan_event["incident_id"] == incident_id
        assert plan_event["version"] == 2
        assert plan_event["payload"]["status"] == "AWAITING_APPROVAL"

        approval_response = client.post(
            f"/api/v1/plans/{plan['id']}/approve",
            json={
                "expected_incident_version": plan["incident_version"],
                "expected_plan_version": plan["plan_version"],
                "operator_reference": "phase03-live-approver",
            },
        )
        assert approval_response.status_code == 200, approval_response.text
        approval = approval_response.json()

        approved_event = websocket.receive_json()
        assert approved_event["event"] == "plan.approved"
        assert approved_event["incident_id"] == incident_id
        assert approved_event["version"] == 3
        assert approved_event["payload"]["incident"]["status"] == "RESPONSE_ACTIVE"

        route = plan["routes"][0]
        resource_id = route["resource_id"]
        approved_resource = next(
            resource
            for resource in approval["resources"]
            if resource["id"] == resource_id
        )
        movement_response = client.patch(
            f"/api/v1/resources/{resource_id}/movement",
            json={
                "incident_id": incident_id,
                "expected_resource_version": approved_resource["version"],
                "route_progress": 0.5,
                "operator_reference": "phase03-live-simulator",
            },
        )
        assert movement_response.status_code == 200, movement_response.text
        moved_resource = movement_response.json()

        movement_event = websocket.receive_json()
        assert movement_event["event"] == "resource.updated"
        assert movement_event["incident_id"] == incident_id
        assert movement_event["version"] == 4
        assert movement_event["payload"] == moved_resource

    canonical_incident_response = client.get(f"/api/v1/incidents/{incident_id}")
    canonical_resource_response = client.get(f"/api/v1/resources/{resource_id}")
    timeline_response = client.get(f"/api/v1/incidents/{incident_id}/timeline")

    assert canonical_incident_response.status_code == 200
    assert canonical_resource_response.status_code == 200
    assert timeline_response.status_code == 200

    canonical_incident = canonical_incident_response.json()
    canonical_resource = canonical_resource_response.json()
    timeline = timeline_response.json()

    assert canonical_incident["id"] == incident_id
    assert canonical_incident["status"] == "RESPONSE_ACTIVE"
    assert canonical_incident["version"] == approval["incident"]["version"]
    assert canonical_incident["location"] == incident["location"]
    assert canonical_incident["provenance"]["source"] == "operator_manual_entry"
    assert canonical_incident["provenance"]["data_reality"] == "SIMULATED"
    assert canonical_incident["provenance"]["freshness_status"] == "FRESH"

    assert canonical_resource == moved_resource
    assert canonical_resource["id"] == resource_id
    assert canonical_resource["status"] == "ASSIGNED"
    assert canonical_resource["assigned_incident_id"] == incident_id
    assert canonical_resource["route_progress"] == 0.5
    assert canonical_resource["provenance"]["source"] == "operator_movement_command"
    assert canonical_resource["provenance"]["data_reality"] == "SIMULATED"
    assert canonical_resource["provenance"]["freshness_status"] == "FRESH"
    assert "speed" not in canonical_resource
    assert "eta" not in canonical_resource

    timeline_types = [event["event_type"] for event in timeline]
    assert timeline_types.count("PLAN_APPROVED") == 1
    assert timeline_types.count("RESOURCES_ASSIGNED") == 1
    assert timeline_types.count("RESOURCE_MOVED") == 1


def test_phase03_operations_reconnect_uses_rest_recovery(
    client: TestClient,
    db_session: Session,
) -> None:
    """Reconnect does not replay process-local events; canonical state is recovered through REST."""
    seed_resources(db=db_session)
    reset_operations_stream()

    with client.websocket_connect("/api/v1/ws/operations") as websocket:
        create_response = client.post(
            "/api/v1/intake/manual",
            json=_manual_incident_payload(),
        )
        assert create_response.status_code == 201
        incident = create_response.json()
        first_event = websocket.receive_json()
        assert first_event["version"] == 1

    patch_response = client.patch(
        f"/api/v1/incidents/{incident['id']}/facts",
        json={
            "expected_incident_version": incident["version"],
            "operator_reference": "phase03-recovery-operator",
            "casualty_count": 2,
        },
    )
    assert patch_response.status_code == 200

    canonical_response = client.get(f"/api/v1/incidents/{incident['id']}")
    assert canonical_response.status_code == 200
    canonical = canonical_response.json()
    assert canonical["casualty_count"] == 2
    assert canonical["version"] == incident["version"] + 1

    with client.websocket_connect("/api/v1/ws/operations") as websocket:
        transition_response = client.post(
            f"/api/v1/incidents/{incident['id']}/transition",
            json={
                "target_status": "RESPONSE_PROPOSED",
                "expected_incident_version": canonical["version"],
                "operator_reference": "phase03-recovery-operator",
            },
        )
        assert transition_response.status_code == 200
        next_event = websocket.receive_json()

    assert next_event["version"] == 3
    assert next_event["event"] == "incident.updated"
    assert next_event["payload"] == transition_response.json()

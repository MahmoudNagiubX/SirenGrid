from __future__ import annotations

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


def _create_approved_zero_route(db_session: Session) -> tuple[Incident, EmergencyResource, ResponsePlan]:
    incident = Incident(
        id=str(uuid.uuid4()),
        version=4,
        incident_type="traffic_collision",
        severity=Severity.HIGH,
        confidence_level=ConfidenceLevel.HIGH,
        status=IncidentStatus.RESPONSE_ACTIVE,
        latitude=30.0561,
        longitude=31.3452,
        required_resources_json=[{"resource_type": "AMBULANCE", "count": 1}],
        provenance_json={"source": "zero-route-test", "data_reality": DataReality.SIMULATED.value},
    )
    resource = EmergencyResource(
        id=str(uuid.uuid4()),
        version=2,
        name="Zero Route Ambulance",
        resource_type=ResourceType.AMBULANCE,
        capability_tags_json=[],
        status=ResourceStatus.ASSIGNED,
        latitude=30.0561,
        longitude=31.3452,
        assigned_incident_id=incident.id,
        provenance_json={"source": "zero-route-test"},
    )
    point = [31.3452, 30.0561]
    geometry = {"type": "LineString", "coordinates": [point, point.copy()]}
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
                "resource_type": ResourceType.AMBULANCE.value,
                "route_id": "zero-route",
                "route_geometry": geometry,
                "geometry": geometry,
                "distance_m": 0.0,
                "eta_seconds": 0.0,
            }
        ],
        metrics_json={"max_arrival_eta_seconds": 0.0},
        score_breakdown_json={},
    )
    incident.current_plan_id = plan.id
    db_session.add_all([incident, resource, plan])
    db_session.commit()
    db_session.refresh(incident)
    db_session.refresh(resource)
    return incident, resource, plan


def test_zero_route_movement_reaches_destination_and_expires_alert_truthfully(
    client: TestClient,
    db_session: Session,
) -> None:
    incident, resource, _ = _create_approved_zero_route(db_session)

    moved = client.patch(
        f"/api/v1/resources/{resource.id}/movement",
        json={
            "incident_id": incident.id,
            "expected_resource_version": resource.version,
            "route_progress": 0.5,
            "operator_reference": "zero-route-movement",
        },
    )

    assert moved.status_code == 200, moved.text
    body = moved.json()
    assert body["route_progress"] == 0.5
    assert body["longitude"] == 31.3452
    assert body["latitude"] == 30.0561
    assert body["provenance"]["movement"]["route_progress"] == 0.5
    alert = client.get(
        f"/api/v1/incidents/{incident.id}/resources/{resource.id}/driver-alert"
    )
    assert alert.status_code == 200, alert.text
    assert alert.json()["status"] == "EXPIRED"
    assert alert.json()["geometry"] is None


def test_zero_route_corridor_is_empty_and_schema_valid(
    client: TestClient,
    db_session: Session,
) -> None:
    incident, resource, _ = _create_approved_zero_route(db_session)

    corridor = client.post(
        f"/api/v1/incidents/{incident.id}/corridor",
        json={"resource_id": resource.id},
    )

    assert corridor.status_code == 200, corridor.text
    body = corridor.json()
    assert body["route_geometry"]["coordinates"] == [[31.3452, 30.0561], [31.3452, 30.0561]]
    assert body["signals"] == []


def test_zero_route_driver_alert_refresh_returns_expired_no_region(
    client: TestClient,
    db_session: Session,
) -> None:
    incident, resource, plan = _create_approved_zero_route(db_session)
    resource.provenance_json = {
        "movement": {
            "incident_id": incident.id,
            "plan_id": plan.id,
            "route_id": "zero-route",
            "route_progress": 0.5,
        }
    }
    db_session.commit()

    refreshed = client.post(
        f"/api/v1/incidents/{incident.id}/resources/{resource.id}/driver-alert/refresh",
        json={
            "expected_resource_version": resource.version,
            "operator_reference": "zero-route-alert",
        },
    )

    assert refreshed.status_code == 200, refreshed.text
    assert refreshed.json()["status"] == "EXPIRED"
    assert refreshed.json()["geometry"] is None

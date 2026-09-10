from __future__ import annotations

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

import app.models as _models  # noqa: F401
from app.db import init_db
from app.main import app
from app.models import DriverAlert, EmergencyResource
from app.driver_alert import build_forward_alert_geometry
from app.schemas import ResourceStatus
from test_phase05_hospital_api import _create_approved_transport_plan


@pytest.fixture(autouse=True)
def setup_isolated_db_tables(isolated_engine: Engine) -> None:
    init_db(isolated_engine)


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def _move(client: TestClient, incident_id: str, resource_id: str, version: int, progress: float):
    return client.patch(
        f"/api/v1/resources/{resource_id}/movement",
        json={
            "incident_id": incident_id,
            "expected_resource_version": version,
            "route_progress": progress,
            "operator_reference": "operator-driver-alert",
        },
    )


def test_zero_distance_approved_route_has_no_forward_alert_geometry() -> None:
    route = {"type": "LineString", "coordinates": [[31.3304, 30.0571], [31.3304, 30.0571]]}

    assert build_forward_alert_geometry(route, 0.5) is None


def test_movement_updates_forward_simulated_driver_alert_and_route_end_expires(
    client: TestClient,
    db_session: Session,
) -> None:
    incident, resource, _ = _create_approved_transport_plan(db_session)

    moved = _move(client, incident.id, resource.id, resource.version, 0.2)
    assert moved.status_code == 200, moved.text
    first = client.get(f"/api/v1/incidents/{incident.id}/resources/{resource.id}/driver-alert")
    assert first.status_code == 200, first.text
    first_data = first.json()
    assert first_data["status"] == "ACTIVE"
    assert first_data["route_progress"] == 0.2
    assert first_data["geometry"]["type"] == "Polygon"
    assert first_data["data_reality"] == "SIMULATED"
    assert first_data["provenance"]["lookahead_m"] == 500
    assert first_data["provenance"]["buffer_m"] == 30
    assert first_data["provenance"]["expiry_seconds"] == 120
    assert "patient_count" not in first_data
    assert "diagnosis" not in first_data

    moved_again = _move(client, incident.id, resource.id, 3, 0.7)
    assert moved_again.status_code == 200, moved_again.text
    current = client.get(f"/api/v1/incidents/{incident.id}/resources/{resource.id}/driver-alert").json()
    assert current["status"] == "ACTIVE"
    assert current["route_progress"] == 0.7
    db_session.expire_all()
    alerts = db_session.scalars(
        select(DriverAlert).where(DriverAlert.incident_id == incident.id).order_by(DriverAlert.created_at.asc())
    ).all()
    assert len(alerts) == 2
    assert alerts[0].status == "EXPIRED"
    assert alerts[1].status == "ACTIVE"

    ended = _move(client, incident.id, resource.id, 4, 1.0)
    assert ended.status_code == 200, ended.text
    terminal = client.get(f"/api/v1/incidents/{incident.id}/resources/{resource.id}/driver-alert")
    assert terminal.status_code == 200
    assert terminal.json()["status"] == "EXPIRED"
    assert terminal.json()["geometry"] is None


def test_explicit_driver_alert_refresh_is_version_checked_without_mutating_resource(
    client: TestClient,
    db_session: Session,
) -> None:
    incident, resource, _ = _create_approved_transport_plan(db_session)
    moved = _move(client, incident.id, resource.id, resource.version, 0.4)
    assert moved.status_code == 200
    resource_version = moved.json()["version"]

    refreshed = client.post(
        f"/api/v1/incidents/{incident.id}/resources/{resource.id}/driver-alert/refresh",
        json={"expected_resource_version": resource_version, "operator_reference": "operator-refresh"},
    )
    assert refreshed.status_code == 200, refreshed.text
    assert refreshed.json()["status"] == "ACTIVE"
    db_session.expire_all()
    persisted = db_session.get(EmergencyResource, resource.id)
    assert persisted is not None
    assert persisted.version == resource_version
    assert persisted.status is ResourceStatus.ASSIGNED
    assert persisted.assigned_incident_id == incident.id

    stale = client.post(
        f"/api/v1/incidents/{incident.id}/resources/{resource.id}/driver-alert/refresh",
        json={"expected_resource_version": resource_version - 1, "operator_reference": "operator-refresh"},
    )
    assert stale.status_code == 409


def test_aggregate_operational_state_exposes_current_phase05_references(
    client: TestClient,
    db_session: Session,
) -> None:
    incident, resource, _ = _create_approved_transport_plan(db_session)
    moved = _move(client, incident.id, resource.id, resource.version, 0.25)
    assert moved.status_code == 200

    aggregate = client.get(f"/api/v1/incidents/{incident.id}/operational-state")

    assert aggregate.status_code == 200, aggregate.text
    data = aggregate.json()
    assert data["incident_id"] == incident.id
    assert data["plan_id"] is not None
    assert len(data["driver_alerts"]) == 1
    assert data["driver_alerts"][0]["resource_id"] == resource.id
    assert data["driver_alert"]["id"] == data["driver_alerts"][0]["id"]
